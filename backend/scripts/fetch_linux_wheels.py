import urllib.request
import json
import sys
import os
import zipfile
import hashlib
import base64
from pathlib import Path

prev_version = os.environ["PREV_VERSION"]
new_version = os.environ.get("NEW_VERSION", prev_version)
url = f"https://pypi.org/pypi/vicoa/{prev_version}/json"
try:
    with urllib.request.urlopen(url) as r:
        data = json.load(r)
except Exception as e:
    print(f"Failed to fetch PyPI metadata: {e}", file=sys.stderr)
    sys.exit(1)

urls = [
    f
    for f in data["urls"]
    if f["packagetype"] == "bdist_wheel"
    and "linux" in f["filename"]
    and "x86_64" in f["filename"]
]
if not urls:
    print("No Linux x86_64 wheels found on PyPI for this version", file=sys.stderr)
    sys.exit(1)

# A single py3-none-<platform> wheel is valid for every Python 3.x, so its
# presence alone is a complete Linux set — reuse it directly. This is the tag
# scheme setup.py now emits (one wheel per arch instead of four cpXY copies).
has_py3_none = any("-py3-none-" in f["filename"] for f in urls)

# Legacy path: for versions published under the old cpXY-cpXY tags, require all
# expected CPython versions to be present on PyPI. If the previous release was
# sparse (e.g. v1.5.6 only published cp310-manylinux), reusing it would
# propagate the sparsity: cibuildwheel is skipped when this script succeeds, so
# any missing cpXY-manylinux wheel never gets built for the new release. Exit
# non-zero so release.yml falls back to the npm reuse path, which lets
# cibuildwheel run and build the wheel(s) fresh.
if not has_py3_none:
    EXPECTED_PY_TAGS = {"cp310", "cp311", "cp312", "cp313"}
    found_py_tags = {
        tag for f in urls for tag in EXPECTED_PY_TAGS if f"-{tag}-" in f["filename"]
    }
    missing = EXPECTED_PY_TAGS - found_py_tags
    if missing:
        print(
            f"PyPI v{prev_version} is missing Linux wheels for: {sorted(missing)}. "
            "Falling through so cibuildwheel can rebuild the full set.",
            file=sys.stderr,
        )
        sys.exit(1)

wheelhouse = Path("wheelhouse")
wheelhouse.mkdir(exist_ok=True)


def sha256_hash(data_bytes: bytes) -> str:
    digest = hashlib.sha256(data_bytes).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def repack_wheel(tmp_path: Path, new_path: Path) -> None:
    # First pass: collect all file contents with version updated
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(tmp_path, "r") as zin:
        for item in zin.infolist():
            data_bytes = zin.read(item.filename)
            new_name = item.filename.replace(prev_version, new_version, 1)
            if item.filename.endswith(("METADATA", "WHEEL")):
                data_bytes = data_bytes.replace(
                    prev_version.encode(), new_version.encode()
                )
            files[new_name] = data_bytes

    # Rebuild RECORD with correct hashes (RECORD itself is always empty-hash by convention)
    record_key = next(k for k in files if k.endswith("RECORD"))
    old_record = files[record_key].decode()
    new_record_lines = []
    for line in old_record.splitlines():
        parts = line.split(",")
        if len(parts) != 3:
            new_record_lines.append(line)
            continue
        file_path = parts[0].replace(prev_version, new_version, 1)
        if file_path == record_key:
            # RECORD entry for itself is always empty
            new_record_lines.append(f"{file_path},,")
        elif file_path in files:
            new_record_lines.append(
                f"{file_path},{sha256_hash(files[file_path])},{len(files[file_path])}"
            )
        else:
            new_record_lines.append(f"{file_path},{parts[1]},{parts[2]}")
    files[record_key] = "\n".join(new_record_lines).encode()

    with zipfile.ZipFile(new_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data_bytes in files.items():
            zout.writestr(name, data_bytes)


for f in urls:
    old_filename = f["filename"]
    tmp_path = wheelhouse / f"_tmp_{old_filename}"
    print(f"Downloading {old_filename}")
    urllib.request.urlretrieve(f["url"], tmp_path)

    if new_version == prev_version:
        tmp_path.rename(wheelhouse / old_filename)
        continue

    new_filename = old_filename.replace(prev_version, new_version, 1)
    new_path = wheelhouse / new_filename
    repack_wheel(tmp_path, new_path)
    tmp_path.unlink()
    print(f"Repacked as {new_filename}")

print(f"Done: {len(urls)} Linux wheels ready in wheelhouse/")
