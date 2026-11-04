"""Locate the MediaPipe ``.task`` model bundles and the Haar cascade.

The models are large binaries (3.7 MB, 7.8 MB and a 0.9 MB cascade) that live
next to the source tree rather than inside the package, so the locator has two
jobs and one honest limitation.

It searches, in order:

1. ``$RVM_MODELS_DIR`` -- an explicit override;
2. ``models/<name>`` in any parent of this file, which is what a source
   checkout looks like.

The limitation: the built wheel does **not** carry ``models/`` (only
``rvm/web`` is declared as package data, because a 12 MB model file inside a
wheel is not something an installer should spring on someone).  A deployment
that installs the package rather than using the checkout therefore has to set
``RVM_MODELS_DIR``; without it every analyser reports ``unavailable`` with that
reason, which is the intended failure.

A missing file raises :class:`FileNotFoundError`; the analysers turn that into
"unavailable" rather than crashing the stream, because a monitoring system that
stops because an optional model is absent is worse than one that says so.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["model_path", "models_dir"]


def models_dir() -> Path | None:
    """The directory holding the ``.task`` models, or ``None`` if not found."""
    override = os.environ.get("RVM_MODELS_DIR")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_dir() else None

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "models"
        if candidate.is_dir():
            return candidate
    return None


def model_path(filename: str) -> Path:
    """Absolute path to ``filename``, or raise :class:`FileNotFoundError`."""
    directory = models_dir()
    if directory is None:
        raise FileNotFoundError(
            f"no models directory found; set RVM_MODELS_DIR to the folder holding {filename}"
        )
    candidate = directory / filename
    if not candidate.is_file():
        raise FileNotFoundError(f"{filename} not found in {directory}")
    return candidate
