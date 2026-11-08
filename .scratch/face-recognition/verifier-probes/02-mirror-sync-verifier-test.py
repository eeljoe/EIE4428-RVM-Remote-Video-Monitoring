"""Killer test for the surviving mutant found in 02 r1 verification.

Mutant: ``StreamSession._publish_faces`` with
``self.face_recognizer.replace_known_faces(faces)`` removed.  The file and the
FaceStore update but the recogniser's in-memory mirror stays stale — a face
registered over HTTP would not be recognised until restart, and a deleted one
would keep matching.  All 541 tests stayed green under that mutant; these
tests pin the store -> recogniser sync directly.
"""

import cv2
import numpy as np

from rvm.server.session import StreamSession

# Same environment workaround as tests/test_face_api.py: OpenCV 4.14 aborts
# in clReleaseDevice at exit after Haar ran on a worker thread.
cv2.ocl.setUseOpenCL(False)


def _session(tmp_path):
    session = StreamSession(
        width=320,
        height=240,
        fps=5.0,
        source=None,
        analysis=True,
        known_faces=tmp_path / "known_faces.json",
    )
    session._models_ready.set()
    session._recent_frames = [
        np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(3)
    ]
    session.face_recognizer.sample_faces = lambda frame: [np.full(8, 2.0)]
    return session


def test_registering_updates_the_recogniser_mirror_immediately(tmp_path):
    session = _session(tmp_path)

    session.register_face("Ada")

    assert set(session.face_recognizer.known_faces) == {"Ada"}
    assert np.allclose(
        session.face_recognizer.known_faces["Ada"], np.full(8, 2.0)
    )


def test_deleting_updates_the_recogniser_mirror_immediately(tmp_path):
    session = _session(tmp_path)
    session.register_face("Ada")
    session.register_face("Bob")

    session.remove_face("Ada")

    assert set(session.face_recognizer.known_faces) == {"Bob"}


def test_store_and_recogniser_agree_after_every_change(tmp_path):
    session = _session(tmp_path)

    for name in ("Ada", "Bob", "Carol"):
        session.register_face(name)
        assert set(session.face_recognizer.known_faces) == set(
            session.face_store.faces
        )
    session.remove_face("Bob")
    assert set(session.face_recognizer.known_faces) == set(
        session.face_store.faces
    )
