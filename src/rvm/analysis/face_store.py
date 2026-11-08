"""The known-face list: names and their embeddings, persisted as JSON.

The list is a *registry of people*, not a cache: losing it means the demo has
to be re-registered, so two properties matter more than the format.

**A missing or broken file is not an error.**  The server starts with an empty
list and says so in the log.  Refusing to stream because a registry is
unreadable would trade a degraded dashboard for no dashboard at all, and the
file is written by the same program that reads it, so a broken one is a bug to
report rather than a condition to die on.

**A write is all-or-nothing.**  Saving goes to a temporary file in the same
directory and is then moved over the target with :func:`os.replace`, which is
atomic on the same filesystem.  A reader therefore sees either the old list or
the new one -- never a half-written file, and never a missing one: the window
where the old file is deleted and the new one is not yet in place does not
exist.

The in-memory mapping is replaced wholesale (``self._faces = ...``) rather than
mutated.  The encode thread iterates it while identifying a picture, and an
in-place insert or delete is exactly what makes a Python dict raise
``dictionary changed size during iteration``.

Only names and vectors are stored, never pictures: the list identifies people,
and a folder of faces is personal data the public repository should not carry.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np

__all__ = ["DEFAULT_KNOWN_FACES", "FaceStore", "FaceStoreError"]

log = logging.getLogger(__name__)

#: Where the list lives unless ``--known-faces`` says otherwise.  Relative to
#: the working directory the server was started in.
DEFAULT_KNOWN_FACES = Path("data") / "known_faces.json"

#: Written into the file so a future format change can be detected rather than
#: guessed at.
FORMAT_VERSION = 1


class FaceStoreError(RuntimeError):
    """The list could not be written; the file on disk is unchanged."""


class FaceStore:
    """Names and embeddings, loadable and atomically saveable."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_KNOWN_FACES
        self._faces: dict[str, np.ndarray] = {}

    @property
    def faces(self) -> dict[str, np.ndarray]:
        """The current mapping.  Treat it as read-only: it is replaced, not edited."""
        return self._faces

    def names(self) -> list[str]:
        """Registered names in a stable order, so responses and files agree."""
        return sorted(self._faces)

    def load(self) -> dict[str, np.ndarray]:
        """Read the file, falling back to an empty list and a warning."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # The normal first run: no registry yet, not a problem.
            self._faces = {}
            return self._faces
        except OSError as exc:
            log.warning(
                "known-face list %s could not be read (%s); starting with an empty list",
                self.path,
                exc,
            )
            self._faces = {}
            return self._faces

        try:
            faces = self._parse(text)
        except (ValueError, TypeError) as exc:
            log.warning(
                "known-face list %s is corrupt (%s); starting with an empty list",
                self.path,
                exc,
            )
            faces = {}

        self._faces = faces
        return self._faces

    def save(self) -> None:
        """Write the list atomically, or raise :class:`FaceStoreError`."""
        payload = json.dumps(
            {
                "version": FORMAT_VERSION,
                "faces": {
                    name: [float(value) for value in self._faces[name]]
                    for name in self.names()
                },
            },
            ensure_ascii=False,
        )

        directory = self.path.parent
        temporary: Path | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(
                dir=directory, prefix=self.path.name + ".", suffix=".tmp"
            )
            temporary = Path(name)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except OSError as exc:
            raise FaceStoreError(f"could not write {self.path}: {exc}") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:  # pragma: no cover - the failure is already reported
                    pass

    def add(self, name: str, embedding) -> None:
        """Register *name*, replacing the mapping rather than editing it."""
        faces = dict(self._faces)
        faces[name] = np.asarray(embedding, dtype=np.float64)
        self._faces = faces

    def remove(self, name: str) -> bool:
        """Forget *name*; returns whether it was registered."""
        if name not in self._faces:
            return False
        faces = dict(self._faces)
        del faces[name]
        self._faces = faces
        return True

    def replace(self, faces) -> None:
        """Install a whole mapping in one assignment."""
        self._faces = {
            str(name): np.asarray(vector, dtype=np.float64)
            for name, vector in faces.items()
        }

    @staticmethod
    def _parse(text: str) -> dict[str, np.ndarray]:
        """Validate the stored shape; anything unexpected is corrupt."""
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object at the top level")
        entries = payload.get("faces")
        if not isinstance(entries, dict):
            raise ValueError('expected a "faces" object')

        faces: dict[str, np.ndarray] = {}
        for name, values in entries.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"invalid name {name!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"invalid embedding for {name!r}")
            vector = np.asarray(values, dtype=np.float64)
            if vector.ndim != 1 or not np.all(np.isfinite(vector)):
                raise ValueError(f"invalid embedding for {name!r}")
            faces[name] = vector
        return faces
