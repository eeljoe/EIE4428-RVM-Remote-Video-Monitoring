"""Tests for the delivery archive whitelist.

The zip is the graded artefact, so a file missing from the whitelist costs
nothing locally and everything at the marker: the zip that was built on 10-26
shipped without ``models/``, which turns face detection and gesture recognition
into "detector unavailable" on a machine that has nothing to download from.

These tests pin the runtime-critical members and the local-only state that must
stay out.  They also run inside the extracted archive during
``tools/make_zip.py`` verification, so a whitelist regression fails the build
instead of travelling to the marker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import make_zip  # noqa: E402  (tools/ is not an installed package)


REQUIRED_MEMBERS = [
    "README.md",
    "DELIVERY.md",
    "run.bat",
    "run_server.py",
    "requirements.txt",
    "requirements-analysis.txt",
    "models/haarcascades/haarcascade_frontalface_default.xml",
    "models/face_landmarker.task",
    "models/hand_landmarker.task",
    "docs/FEATURES.md",
    "docs/EIE4428-mini-project-report-RVM.docx",
]

LOCAL_ONLY = [
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    "tests/scenegen.pyc",
    "data/known_faces.json",
    "recordings/",
    "Mini-Project-webcam-26.pdf",
    "mc26-lecture",
    ".scratch/",
]


@pytest.fixture(scope="module")
def members() -> set[str]:
    """Archive-relative names, with the top-level folder stripped."""
    return {arcname.split("/", 1)[1] for arcname, _ in make_zip.collect()}


@pytest.mark.parametrize("member", REQUIRED_MEMBERS)
def test_the_archive_carries_every_runtime_asset(members, member):
    assert member in members, f"{member} missing from the delivery whitelist"


@pytest.mark.parametrize("member", LOCAL_ONLY)
def test_local_only_state_stays_out_of_the_archive(members, member):
    leaked = [name for name in members if member in name]

    assert not leaked, f"local-only path leaked into the archive: {leaked}"


def test_the_archive_drags_no_lecture_material(members):
    """The five lecture PDFs and the task brief are not ours to redistribute."""
    pdfs = [name for name in members if name.lower().endswith(".pdf")]

    assert not pdfs, f"PDFs leaked into the archive: {pdfs}"
