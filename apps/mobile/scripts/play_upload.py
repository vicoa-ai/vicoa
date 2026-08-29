#!/usr/bin/env python3
"""Upload a release AAB to Google Play, or promote an uploaded build to rollout.

Auth is a Google Play service-account JSON key requested with the
`androidpublisher` scope -- the same credential the app-pricing-apply skill uses.
Pass it via --key or the GOOGLE_PLAY_KEY env var. The service account needs
"Release to production" / "Release to testing tracks" access to the app.

Two modes:

  # 1. Upload the AAB and stage it as a DRAFT release (default: not rolled out).
  python3 scripts/play_upload.py --key ~/play-sa.json

  # 2. After reviewing in Play Console, promote the uploaded build to a live
  #    rollout (full, or a staged fraction).
  python3 scripts/play_upload.py --key ~/play-sa.json --promote --version-code 32
  python3 scripts/play_upload.py --key ~/play-sa.json --promote --version-code 32 --rollout 0.1

The edits API is transactional: nothing is persisted until commit(), so a failure
mid-way leaves the store untouched.
"""
import argparse
import os
import sys

DEFAULT_PACKAGE = "app.vicoa"
DEFAULT_AAB = "build/app/outputs/bundle/release/app-release.aab"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"


def client(key_path: str):
    import httplib2
    import google_auth_httplib2
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(os.path.expanduser(key_path), scopes=[SCOPE])
    # A generous socket timeout so a slow chunk upload does not read-timeout.
    authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=600))
    return build("androidpublisher", "v3", http=authed_http, cache_discovery=False)


def build_release(version_code: int, name: str, status: str, rollout: float | None) -> dict:
    release = {"name": name, "versionCodes": [str(version_code)], "status": status}
    if status == "inProgress":
        if rollout is None:
            sys.exit("--rollout <fraction 0..1> is required when status is inProgress")
        release["userFraction"] = rollout
    return release


def latest_completed_notes(releases: list, exclude_vc: int):
    """releaseNotes of the completed release with the highest version code (excluding exclude_vc)."""
    def maxvc(r):
        return max((int(v) for v in r.get("versionCodes", [])), default=0)
    candidates = [r for r in releases
                  if r.get("status") == "completed" and r.get("releaseNotes")
                  and exclude_vc not in [int(v) for v in r.get("versionCodes", [])]]
    return max(candidates, key=maxvc)["releaseNotes"] if candidates else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload or promote a Google Play release.")
    ap.add_argument("--key", default=os.environ.get("GOOGLE_PLAY_KEY"), help="Service-account JSON path (or env GOOGLE_PLAY_KEY).")
    ap.add_argument("--package", default=DEFAULT_PACKAGE, help=f"Application id (default {DEFAULT_PACKAGE}).")
    ap.add_argument("--aab", default=DEFAULT_AAB, help=f"Path to the .aab (default {DEFAULT_AAB}).")
    ap.add_argument("--track", default="production", help="Release track (default production).")
    ap.add_argument("--status", default="draft", choices=["draft", "completed", "inProgress", "halted"], help="Release status (default draft = uploaded but not rolled out).")
    ap.add_argument("--rollout", type=float, default=None, help="User fraction 0..1 for a staged rollout (status inProgress).")
    ap.add_argument("--release-name", default=None, help="Release name shown in Play Console (default: version code).")
    ap.add_argument("--promote", action="store_true", help="Do NOT upload; set an already-uploaded version code's track release status.")
    ap.add_argument("--version-code", type=int, default=None, help="Version code to promote (required with --promote).")
    ap.add_argument("--copy-notes", action="store_true", help="Copy 'What's new' release notes from the previous release (default: leave blank/optional).")
    args = ap.parse_args()

    if not args.key:
        sys.exit("Provide a service-account key via --key or GOOGLE_PLAY_KEY.")
    if args.promote and args.version_code is None:
        sys.exit("--promote requires --version-code.")
    if not args.promote and not os.path.isfile(args.aab):
        sys.exit(f"AAB not found: {args.aab}")

    svc = client(args.key)
    edit_id = svc.edits().insert(packageName=args.package, body={}).execute()["id"]

    if args.promote:
        version_code = args.version_code
        print(f"Promoting version code {version_code} on '{args.track}' to status '{args.status}'...")
    else:
        from googleapiclient.http import MediaFileUpload
        # Non-resumable single upload: httplib2 mishandles the resumable protocol's
        # HTTP 308 (treats it as a redirect and raises RedirectMissingLocation).
        # The generous socket timeout on the http client covers the single large PUT.
        media = MediaFileUpload(args.aab, mimetype="application/octet-stream", resumable=False)
        print(f"Uploading {args.aab} to {args.package} (this can take a minute) ...")
        response = svc.edits().bundles().upload(packageName=args.package, editId=edit_id, media_body=media).execute(num_retries=5)
        version_code = response["versionCode"]
        print(f"Uploaded bundle: versionCode={version_code}")

    name = args.release_name or f"{version_code}"
    release = build_release(version_code, name, args.status, args.rollout)

    # Release notes are optional and left blank by default. Keep any notes already
    # on this release; only copy from the previous release when --copy-notes is given.
    # Play preserves the live release automatically, so the update carries only the target.
    existing = svc.edits().tracks().get(packageName=args.package, editId=edit_id, track=args.track).execute().get("releases", [])
    current = next((r for r in existing if version_code in [int(v) for v in r.get("versionCodes", [])]), None)
    if current and current.get("releaseNotes"):
        release["releaseNotes"] = current["releaseNotes"]
    elif args.copy_notes:
        prev = latest_completed_notes(existing, exclude_vc=version_code)
        if prev:
            release["releaseNotes"] = prev
            print(f"Copied release notes from previous release ({', '.join(n['language'] for n in prev)}).")
        else:
            print("No previous release notes found to copy.")

    svc.edits().tracks().update(packageName=args.package, editId=edit_id, track=args.track, body={"track": args.track, "releases": [release]}).execute()
    svc.edits().commit(packageName=args.package, editId=edit_id).execute()

    verb = "rolled out" if args.status in ("completed", "inProgress") else "staged as draft"
    print(f"Committed: versionCode {version_code} on '{args.track}' {verb} (status={args.status}).")
    if args.status == "draft":
        print("Draft is in Play Console but NOT live. Review it, then run with --promote --version-code "
              f"{version_code} --status completed to roll out.")


if __name__ == "__main__":
    main()
