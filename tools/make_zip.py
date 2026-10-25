"""Build the course delivery ZIP for the RVM mini project.

The brief (``Mini-Project-webcam-26.pdf``, p.5) asks for "a zip file containing
all source codes and executable files".  The archive is assembled from an
explicit whitelist, so three classes of file can never reach the marker:

* local environment artefacts -- ``.venv/``, ``__pycache__/``, ``.pytest_cache/``
* course material -- the five lecture PDFs and the task brief (not ours to
  redistribute, and 15.9 MB of dead weight)
* agent working notes -- ``docs/wiki/``, ``docs/STATUS.md``, ``ROADMAP.md``

The build is self-checking: the archive is extracted into a temporary directory
and the full test suite is executed *there*, so a delivery package that cannot
actually run is caught at build time rather than in the marker.

Usage::

    python tools/make_zip.py                     # -> dist/EIE4428-RVM.zip
    python tools/make_zip.py --out D:/downloads
    python tools/make_zip.py --out D:/downloads --no-verify
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "EIE4428-RVM"  # top-level folder inside the archive

# --- explicit whitelist ----------------------------------------------------
# Single files copied verbatim from the project root.
ROOT_FILES = [
    "README.md",
    "DELIVERY.md",
    "requirements.txt",
    "requirements-dev.txt",
    "run.bat",
    "run_server.py",
    "verify_system.py",
    "pyproject.toml",
    # The course template is required by tools/build_report.py and by
    # tests/test_report.py, which rebuilds the report from it.
    "EIE4428-mini-project-report-template.docx",
]

# Whole directories copied recursively.
TREE_DIRS = [
    "src",
    "tests",
    "tools",
    "docs/figures",
]

# Individual files inside directories that are not copied wholesale.
EXTRA_FILES = [
    "docs/EIE4428-mini-project-report-RVM.docx",
]

# Never include anything matching these, wherever it appears.
SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp"}

# Sanity net: the finished archive must not contain any of these.
FORBIDDEN = [
    ".venv",
    "__pycache__",
    "mc26-lecture",
    "Mini-Project-webcam-26.pdf",
    ".pytest_cache",
]


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


def _skip(path: Path) -> bool:
    if path.name in SKIP_DIR_NAMES or path.name.startswith("."):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def collect() -> list[tuple[str, Path]]:
    """Return ``(arcname, source_path)`` pairs for every file to be packed."""
    items: list[tuple[str, Path]] = []
    missing: list[str] = []

    for rel in ROOT_FILES + EXTRA_FILES:
        src = ROOT / rel
        if src.is_file():
            items.append((f"{TOP}/{rel}", src))
        else:
            missing.append(rel)

    for d in TREE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            missing.append(f"{d}/ (directory)")
            continue
        for src in sorted(base.rglob("*")):
            if not src.is_file() or _skip(src):
                continue
            rel = src.relative_to(ROOT).as_posix()
            items.append((f"{TOP}/{rel}", src))

    if missing:
        raise SystemExit(
            "[ERROR] Expected delivery inputs are missing:\n  - "
            + "\n  - ".join(missing)
        )
    return items


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def build(out: Path, items: list[tuple[str, Path]]) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for arcname, src in sorted(items, key=lambda pair: pair[0]):
            info = zipfile.ZipInfo(arcname, date_time=time.localtime(src.stat().st_mtime)[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # regular file, rw-r--r--
            zf.writestr(info, src.read_bytes())
    return out


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def audit_members(archive: Path) -> list[str]:
    """Return the list of forbidden members that slipped into the archive."""
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    return [
        name
        for name in names
        for bad in FORBIDDEN
        if bad in name.replace("\\", "/")
    ]


def verify(archive: Path, python_exe: str) -> tuple[bool, str]:
    """Extract the archive and run the test suite inside the extracted copy."""
    with tempfile.TemporaryDirectory(prefix="rvm-zip-verify-") as tmp:
        target = Path(tmp)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
        root = target / TOP
        if not root.is_dir():
            return False, f"top-level folder {TOP}/ missing from the archive"

        for rel in ROOT_FILES + EXTRA_FILES:
            if not (root / rel).is_file():
                return False, f"extracted archive is missing {rel}"
        for d in TREE_DIRS:
            if not (root / d).is_dir():
                return False, f"extracted archive is missing {d}/"

        try:
            proc = subprocess.run(
                # no extra -q: pyproject already sets it, and "-q -q" hides the summary
                [python_exe, "-m", "pytest"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except subprocess.TimeoutExpired:
            return False, "the test suite did not finish within 900 s"

        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        summary = tail[-1] if tail else "(no output)"
        if proc.returncode != 0:
            return False, f"tests failed inside the extracted archive\n{summary}"
        return True, summary


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(ROOT / "dist"),
        help="output directory or .zip path (default: <project>/dist)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the extract-and-test verification step",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="interpreter used to run the test suite during verification",
    )
    args = parser.parse_args()

    out = Path(args.out).expanduser()
    if out.is_dir() or not out.suffix:
        out = out / "EIE4428-RVM.zip"
    out = out.resolve()

    items = collect()
    archive = build(out, items)

    size_kb = archive.stat().st_size / 1024
    print(f"Built  {archive}")
    print(f"       {len(items)} files, {size_kb:.1f} KB")

    leaked = audit_members(archive)
    if leaked:
        print("[FAIL] forbidden members in the archive:")
        for name in leaked:
            print(f"       {name}")
        return 1
    print("       content audit OK (no .venv / caches / lecture PDFs)")

    if args.no_verify:
        print("       verification skipped (--no-verify)")
        return 0

    ok, summary = verify(archive, args.python)
    print(f"       extracted-and-tested: {summary}")
    if not ok:
        print("[FAIL] the archive does not run cleanly")
        return 1
    print("[OK]   delivery package verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
