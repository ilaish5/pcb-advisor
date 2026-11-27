"""Download the frozen 27/11 fixture from the GitHub release into local/acceptance-fixtures/ (for cloud sessions and new
checkouts). The zip hash is checked here; run.py then checks every file against MANIFEST.sha256.

    python -I tests/acceptance/fetch_fixture.py
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
URL = ("https://github.com/ilaish5/pcb-advisor/releases/download/fixture-final-e2e-4l-1127/final-e2e-4l-1127.zip")
ZIP_SHA = "21c899044ce23350742a4c19273f70a0c32966349e373a3c58806acdeba07477"
DEST = REPO / "local" / "acceptance-fixtures"


def main() -> int:
    target = DEST / "final-e2e-4l-1127"
    if (target / "MANIFEST.sha256").is_file():
        print(f"already present: {target} (run.py verifies it)")
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        z = pathlib.Path(tmp) / "fixture.zip"
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as r, open(z, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        h = hashlib.sha256(z.read_bytes()).hexdigest()
        if h != ZIP_SHA:
            print(f"REFUSED: zip sha256 {h} != {ZIP_SHA}")
            return 2
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
                    print(f"REFUSED: unsafe path in zip: {name}")
                    return 2
            zf.extractall(DEST)
    print(f"extracted to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
