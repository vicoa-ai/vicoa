"""`import shared.database` must be enough to use the models.

Seed scripts and one-off tools import the package and nothing else. If a model
module is only reachable through some router's import, a foreign key into its
table can't resolve outside the running app (NoReferencedTableError at flush).
The check runs in a fresh interpreter: inside pytest, conftest has already
imported every router, which would hide the gap.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

CHECK = """
import shared.database as db

for table in db.Base.metadata.sorted_tables:
    for fk in table.foreign_keys:
        _ = fk.column  # NoReferencedTableError when the target isn't registered
print("ok")
"""


def test_models_package_resolves_every_foreign_key(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=tmp_path,  # no .env here for Settings to pick up
        env={"PYTHONPATH": str(SRC), "HOME": os.environ.get("HOME", str(tmp_path))},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "ok"
