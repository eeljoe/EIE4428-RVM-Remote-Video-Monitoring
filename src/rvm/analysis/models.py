"""Locate the MediaPipe ``.task`` model bundles the analysers need.

The models are large binaries (3.7 MB and 7.8 MB) that ship next to the source
tree rather than inside the package, so the locator has to work for a checkout
and for an installed copy.  It searches, in order:

1. ``$RVM_MODELS_DIR`` -- an explicit override, which is the escape hatch for
   a deployed copy that does not keep the repository layout;
2. ``models/<name>`` in any parent of this file, which is what a source
   checkout looks like.

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
