#!/usr/bin/env python3
"""
Build and optionally publish npm packages for @vicoa/cli.

Platform variants are published as version-tagged releases of the same
@vicoa/cli package (e.g. @vicoa/cli@1.3.10-darwin-arm64), matching the
pattern used by @openai/codex.

Usage:
  # Build a platform variant
  python scripts/build_npm_package.py \
    --platform darwin-arm64 \
    --dist-dir pyinstaller/dist/vicoa \
    --version 1.3.10

  # Build and publish a platform variant
  python scripts/build_npm_package.py \
    --platform darwin-arm64 \
    --dist-dir pyinstaller/dist/vicoa \
    --version 1.3.10 \
    --publish

  # Build and publish the main shim package
  python scripts/build_npm_package.py \
    --main-only \
    --version 1.3.10 \
    --publish
"""

import argparse
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PLATFORMS = {
    "darwin-arm64": {"os": "darwin", "cpu": "arm64", "binary": "vicoa"},
    "darwin-x64": {"os": "darwin", "cpu": "x64", "binary": "vicoa"},
    "linux-x64": {"os": "linux", "cpu": "x64", "binary": "vicoa"},
    "win32-x64": {"os": "win32", "cpu": "x64", "binary": "vicoa.exe"},
}

REPO_ROOT = Path(__file__).parent.parent


def build_platform_package(
    platform: str, dist_dir: Path, version: str, output: Path
) -> Path:
    """Generate a platform variant package (@vicoa/cli@{version}-{platform})."""
    if platform not in PLATFORMS:
        print(
            f"Unknown platform: {platform}. Valid: {', '.join(PLATFORMS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    meta = PLATFORMS[platform]
    pkg_version = f"{version}-{platform}"
    pkg_dir = output / f"cli-{platform}"

    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True)

    # Copy the entire onedir dist directory into bin/
    bin_dir = pkg_dir / "bin"
    shutil.copytree(dist_dir, bin_dir)

    # Ensure executable bit on the main binary
    exe = bin_dir / meta["binary"]
    if meta["binary"] != "vicoa.exe":
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Ensure executable bit on embedded agent binaries (codex, opencode, etc.)
    inner_bin_dir = bin_dir / "_internal" / "vicoa" / "_bin"
    if inner_bin_dir.is_dir():
        for inner_bin in inner_bin_dir.rglob("*"):
            if inner_bin.is_file() and inner_bin.suffix == "":
                inner_bin.chmod(
                    inner_bin.stat().st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )

    package_json = {
        "name": "@vicoa/cli",
        "version": pkg_version,
        "description": f"Vicoa CLI - {meta['os']} {meta['cpu']} binary",
        "os": [meta["os"]],
        "cpu": [meta["cpu"]],
        "files": ["bin/"],
        "license": "AGPL-3.0",
    }
    (pkg_dir / "package.json").write_text(json.dumps(package_json, indent=2) + "\n")

    print(f"Built @vicoa/cli@{pkg_version} ->{pkg_dir}")
    return pkg_dir


def build_main_package(version: str, output: Path) -> Path:
    """Generate the main @vicoa/cli shim with optionalDependencies pointing to platform variants."""
    pkg_dir = output / "cli"

    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)

    shutil.copytree(REPO_ROOT / "npm" / "cli", pkg_dir)

    pkg_json_path = pkg_dir / "package.json"
    pkg = json.loads(pkg_json_path.read_text())
    pkg["version"] = version
    pkg["optionalDependencies"] = {
        f"@vicoa/cli-{p}": f"npm:@vicoa/cli@{version}-{p}" for p in PLATFORMS
    }
    pkg_json_path.write_text(json.dumps(pkg, indent=2) + "\n")

    print(f"Built @vicoa/cli@{version} ->{pkg_dir}")
    return pkg_dir


def publish(pkg_dir: Path) -> None:
    pkg = json.loads((pkg_dir / "package.json").read_text())
    print(f"Publishing {pkg['name']}@{pkg['version']}...")
    cmd = ["npm", "publish", str(pkg_dir), "--access", "public", "--tag", "latest"]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build @vicoa/cli npm packages")
    parser.add_argument("--platform", choices=list(PLATFORMS), help="Target platform")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="Path to the PyInstaller onedir output (e.g. pyinstaller/dist/vicoa)",
    )
    parser.add_argument(
        "--version", required=True, help="Package version (e.g. 1.3.10)"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("dist/npm"), help="Output directory"
    )
    parser.add_argument(
        "--publish", action="store_true", help="Publish to npm after building"
    )
    parser.add_argument(
        "--main-only",
        action="store_true",
        help="Build/publish only the main shim package",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    if args.main_only:
        pkg_dir = build_main_package(args.version, args.output)
        if args.publish:
            publish(pkg_dir)
        return

    dist_dir: Path | None = args.dist_dir

    if not args.platform:
        parser.error("--platform is required unless --main-only is set")
    if not dist_dir:
        parser.error("--dist-dir is required unless --main-only is set")
    if not dist_dir.is_dir():
        print(f"dist-dir not found or not a directory: {dist_dir}", file=sys.stderr)
        sys.exit(1)

    pkg_dir = build_platform_package(args.platform, dist_dir, args.version, args.output)
    if args.publish:
        publish(pkg_dir)


if __name__ == "__main__":
    main()
