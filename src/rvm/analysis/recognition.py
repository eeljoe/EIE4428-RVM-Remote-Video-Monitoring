"""Face identification and facial-expression analysis.

Both stages use the same MediaPipe FaceLandmarker *model file*, but each builds
its own landmarker instance: identification needs landmarks only, expression
needs blendshapes, and asking one instance for both would still cost one
inference -- so a face costs two inferences per analysis tick.  That is a
deliberate trade: two small classes with an honest cost beats one class that
serves two payload shapes.

Landmarks give a geometric embedding for "who is this"; blendshapes give
mouth/brow/eye activations for "what does the face look like".

Three things this module deliberately does *not* do.

**It does not train anything.**  Identification compares a landmark-derived
embedding against a small in-memory database.  With an empty database the
honest report is "faces seen, none of them known" -- which is a different
statement from "recognition unavailable", and the two are reported as different
states so the dashboard cannot blur them.

**It does not run per frame.**  One FaceLandmarker call costs tens of
milliseconds; the session calls it on a cadence (see
:class:`rvm.server.session.StreamSession`), not on every picture, because the
video pipeline is the thing being graded.

**It does not report a confidence in any calibrated sense.**  ``1 - distance``
over a 1434-dimensional landmark vector is a similarity score with a usable
ordering and an arbitrary scale; the threshold is a distance cut-off.  It is
reported because a monotone score is still useful on a dashboard, not because
it is a probability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .models import model_path
from .states import (
    STATE_DISABLED,
    STATE_ERROR,
    STATE_NO_FACES,
    STATE_NO_KNOWN,
    STATE_RUNNING,
    STATE_UNAVAILABLE,
)

__all__ = [
    "FaceRecognition",
    "FaceRecognizer",
    "FaceSamplingError",
    "EmotionDetection",
    "EmotionRecognizer",
]

log = logging.getLogger(__name__)

# Reported in place of a detector name when there is nothing to report; the
# vocabulary lives in :mod:`rvm.analysis.states` so every analyser agrees.


class FaceSamplingError(RuntimeError):
    """No sample could be taken: the landmarker is missing or the frame failed.

    Registration needs to tell "this frame has no face" (an answer about the
    scene, which the operator can fix by standing in front of the camera) from
    "there is no landmarker" (an answer about the installation, which no amount
    of standing still will fix).  The first is an empty list, the second is
    this exception.
    """


def _ensure_rgb(frame: np.ndarray) -> np.ndarray:
    """Return an RGB view of *frame*.

    Frames from :mod:`rvm.server.source` are already RGB, so converting with
    ``COLOR_BGR2RGB`` would silently swap red and blue and destroy the colour
    cues MediaPipe uses.  Only single-channel input needs converting.
    """
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    return np.ascontiguousarray(frame)


@dataclass
class FaceRecognition:
    """Recognised faces: identity, confidence and where each was found."""

    identities: List[Tuple[str, float, Tuple[int, int, int, int]]] = field(
        default_factory=list
    )  # (name, confidence, (x, y, w, h))
    state: str = STATE_DISABLED
    #: How many faces the landmarker saw, whether or not any matched.  Without
    #: it "no known faces registered" and "nobody in view" would look the same.
    seen: int = 0

    @property
    def count(self) -> int:
        return len(self.identities)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "seen": self.seen,
            "identities": [
                {"name": name, "confidence": round(conf, 3), "bbox": list(bbox)}
                for name, conf, bbox in self.identities
            ],
            "state": self.state,
        }


@dataclass
class EmotionDetection:
    """Classified expressions with confidence scores."""

    emotions: List[Tuple[str, float, Tuple[int, int, int, int]]] = field(
        default_factory=list
    )  # (emotion, confidence, (x, y, w, h))
    state: str = STATE_DISABLED

    @property
    def count(self) -> int:
        return len(self.emotions)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "emotions": [
                {"emotion": emotion, "confidence": round(conf, 3), "bbox": list(bbox)}
                for emotion, conf, bbox in self.emotions
            ],
            "state": self.state,
        }



class _FaceLandmarkerOwner:
    """Shared lazy loading of a MediaPipe FaceLandmarker.

    Subclasses differ only in whether they ask for blendshapes; the loading,
    failure caching and logging are the same and live here once.
    """

    _model_file = "face_landmarker.task"

    def __init__(self, output_blendshapes: bool) -> None:
        self._output_blendshapes = output_blendshapes
        self._model = None
        self._failure: str | None = None

    @property
    def available(self) -> bool:
        return self._load_model() is not None

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self._failure is not None:
            return None

        try:
            from mediapipe.tasks import python as mp_tasks
            from mediapipe.tasks.python import vision as mp_vision

            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(
                    model_asset_path=str(model_path(self._model_file))
                ),
                num_faces=5,
                min_face_detection_confidence=0.5,
                output_face_blendshapes=self._output_blendshapes,
                running_mode=mp_vision.RunningMode.IMAGE,
            )
            self._model = mp_vision.FaceLandmarker.create_from_options(options)
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("%s unavailable: %s", type(self).__name__, self._failure)
        return self._model

    @property
    def unavailable_reason(self) -> str | None:
        """Why the model is not loaded, for the API and the logs."""
        if self._failure is None and self._model is None:
            self._load_model()
        return self._failure

    def close(self) -> None:
        """Release the landmarker and stop reporting availability.

        MediaPipe keeps the model in native memory; a server that closes its
        session without closing this leaves the model resident for the life of
        the process.
        """
        model, self._model = self._model, None
        self._failure = "closed"
        if model is not None:
            try:
                model.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass

    def _detect(self, frame: np.ndarray):
        """Run the landmarker on one RGB frame, or return ``None``."""
        import mediapipe as mp

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=_ensure_rgb(frame))
        return self._model.detect(image)


def _boxes_from_landmarks(face_landmarks, width: int, height: int, pad: int = 0):
    """Bounding box in pixels for one face's landmarks."""
    xs = [lm.x * width for lm in face_landmarks]
    ys = [lm.y * height for lm in face_landmarks]
    x_min = max(0, int(min(xs)) - pad)
    y_min = max(0, int(min(ys)) - pad)
    x_max = min(width, int(max(xs)) + pad)
    y_max = min(height, int(max(ys)) + pad)
    return (x_min, y_min, x_max - x_min, y_max - y_min)


class FaceRecognizer(_FaceLandmarkerOwner):
    """Identify faces against a small in-memory database of known embeddings."""

    def __init__(self, threshold: float = 0.6) -> None:
        super().__init__(output_blendshapes=False)
        self.threshold = threshold
        self.known_faces: Dict[str, np.ndarray] = {}

    def add_known_face(self, name: str, embedding: np.ndarray) -> None:
        """Register a face by its landmark embedding.

        The mapping is copied and swapped, never edited in place: the encode
        thread iterates it while identifying a picture, and an insert into a
        dict another thread is walking is what raises ``dictionary changed
        size during iteration``.
        """
        known = dict(self.known_faces)
        known[name] = np.asarray(embedding, dtype=np.float64)
        self.known_faces = known

    def remove_known_face(self, name: str) -> bool:
        """Forget a registered face; returns whether it was there."""
        if name not in self.known_faces:
            return False
        known = dict(self.known_faces)
        del known[name]
        self.known_faces = known
        return True

    def replace_known_faces(self, faces) -> None:
        """Install a whole list at once -- what loading, or a saved change, does."""
        self.known_faces = {
            str(name): np.asarray(vector, dtype=np.float64)
            for name, vector in faces.items()
        }

    def sample_faces(self, frame: np.ndarray) -> List[np.ndarray]:
        """One embedding per face in *frame*; an empty list when there is none.

        Registration averages these over a few frames.  It is deliberately the
        same inference :meth:`recognize` uses, so a face that can be registered
        is a face that can be recognised -- two separate sampling paths would
        eventually disagree about which landmarks count.
        """
        if self._load_model() is None:
            raise FaceSamplingError(self._failure or "face landmarker unavailable")

        try:
            result = self._detect(frame)
        except Exception as exc:  # noqa: BLE001 - any failure means "no sample"
            raise FaceSamplingError(f"{type(exc).__name__}: {exc}") from exc

        samples: List[np.ndarray] = []
        for face_landmarks in result.face_landmarks or []:
            embedding = self._embedding(face_landmarks)
            if embedding is not None:
                samples.append(embedding)
        return samples

    def recognize(self, frame: np.ndarray) -> FaceRecognition:
        """Identify every face in *frame*.

        Without a registered face the result is ``no-known-faces`` rather than
        a list of anonymous hits: the module can see faces but has nothing to
        compare them with, and saying so is more useful than inventing labels.
        """
        if self._load_model() is None:
            return FaceRecognition([], STATE_UNAVAILABLE)

        try:
            result = self._detect(frame)
        except Exception as exc:  # noqa: BLE001 - a bad frame must not stop the stream
            log.warning("face recognition failed: %s", exc)
            return FaceRecognition([], STATE_ERROR)

        if not result.face_landmarks:
            return FaceRecognition([], STATE_NO_FACES, seen=0)

        # One reference for the whole picture: the registry may be replaced by
        # a registration halfway through, and mixing two lists in one result
        # would mean scoring faces against two different databases.
        known = self.known_faces
        seen = len(result.face_landmarks)
        if not known:
            return FaceRecognition([], STATE_NO_KNOWN, seen=seen)

        height, width = frame.shape[:2]
        identities = []
        for face_landmarks in result.face_landmarks:
            embedding = self._embedding(face_landmarks)
            if embedding is None:
                continue
            name, confidence = self._match(embedding, known)
            if name is not None:
                identities.append(
                    (name, confidence, _boxes_from_landmarks(face_landmarks, width, height))
                )
        return FaceRecognition(identities, STATE_RUNNING, seen=seen)

    def _match(
        self, embedding: np.ndarray, known: Dict[str, np.ndarray] | None = None
    ) -> tuple[str | None, float]:
        """The registered name for *embedding*, or ``None`` when nobody is close.

        Keeping the accept/reject rule here rather than inline makes it
        testable: the whole point of the threshold is that a face that is
        merely nearest-but-far is not reported as an identity.
        """
        name, distance = self._nearest(embedding, known)
        confidence = max(0.0, 1.0 - distance)
        if name is None or confidence < self.threshold:
            return None, confidence
        return name, confidence

    def _nearest(
        self, embedding: np.ndarray, known: Dict[str, np.ndarray] | None = None
    ) -> tuple[str | None, float]:
        known = self.known_faces if known is None else known
        best_name = None
        best_distance = float("inf")
        for name, registered in known.items():
            try:
                distance = float(np.linalg.norm(embedding - registered))
            except ValueError:
                # A registered vector of a different width cannot be compared
                # with this one: NumPy refuses to broadcast, and the exception
                # would travel out of the analysis tick and kill the picture
                # pump.  Entries like that come from a file written by another
                # landmarker (or by hand); an unmatched entry is the honest
                # reading of "this list cannot describe this face".
                log.debug(
                    "skipping %r: width %s does not match this face's %s",
                    name,
                    np.shape(registered),
                    embedding.shape,
                )
                continue
            if distance < best_distance:
                best_distance, best_name = distance, name
        return best_name, best_distance


    @staticmethod
    def _embedding(face_landmarks) -> Optional[np.ndarray]:
        """Flatten one face's landmark coordinates into a comparison vector."""
        try:
            values = []
            for landmark in face_landmarks:
                values.extend((landmark.x, landmark.y, landmark.z))
            return np.asarray(values, dtype=np.float64)
        except Exception:  # noqa: BLE001 - malformed landmarks mean "skip this face"
            return None


class EmotionRecognizer(_FaceLandmarkerOwner):
    """Classify facial expression from blendshape activations."""

    EMOTIONS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

    # One weight table, stated once: each expression is a weighted sum of the
    # blendshapes that produce it.  Weights sum to 1.0 per expression so the
    # scores stay comparable, and a dominant score below NEUTRAL_FLOOR is
    # reported as a neutral face rather than as a weak version of something.
    WEIGHTS = {
        "happy": {
            "mouthSmileLeft": 0.3,
            "mouthSmileRight": 0.3,
            "cheekSquintLeft": 0.2,
            "cheekSquintRight": 0.2,
        },
        "sad": {
            "mouthFrownLeft": 0.3,
            "mouthFrownRight": 0.3,
            "browDownLeft": 0.2,
            "browDownRight": 0.2,
        },
        "angry": {
            "browDownLeft": 0.25,
            "browDownRight": 0.25,
            "jawForward": 0.25,
            "mouthPressLeft": 0.125,
            "mouthPressRight": 0.125,
        },
        "surprise": {
            "browOuterUpLeft": 0.25,
            "browOuterUpRight": 0.25,
            "eyeWideLeft": 0.2,
            "eyeWideRight": 0.2,
            "jawOpen": 0.1,
        },
        "fear": {
            "browInnerUp": 0.3,
            "eyeWideLeft": 0.35,
            "eyeWideRight": 0.35,
        },
        "disgust": {
            "noseSneerLeft": 0.35,
            "noseSneerRight": 0.35,
            "mouthUpperUpLeft": 0.15,
            "mouthUpperUpRight": 0.15,
        },
    }

    NEUTRAL_FLOOR = 0.15

    def __init__(self) -> None:
        super().__init__(output_blendshapes=True)

    def detect(self, frame: np.ndarray) -> EmotionDetection:
        """Classify the expression of every face in *frame*."""
        if self._load_model() is None:
            return EmotionDetection([], STATE_UNAVAILABLE)

        try:
            result = self._detect(frame)
        except Exception as exc:  # noqa: BLE001 - a bad frame must not stop the stream
            log.warning("emotion detection failed: %s", exc)
            return EmotionDetection([], STATE_ERROR)

        if not result.face_landmarks:
            return EmotionDetection([], STATE_NO_FACES)

        height, width = frame.shape[:2]
        emotions = []
        for index, face_landmarks in enumerate(result.face_landmarks):
            if index >= len(result.face_blendshapes or []):
                continue
            emotion, confidence = self._classify(result.face_blendshapes[index])
            emotions.append(
                (
                    emotion,
                    confidence,
                    _boxes_from_landmarks(face_landmarks, width, height, pad=20),
                )
            )
        return EmotionDetection(emotions, STATE_RUNNING)

    def _classify(self, blendshapes) -> Tuple[str, float]:
        """Turn one face's blendshape scores into ``(emotion, confidence)``."""
        scores = {bs.category_name: float(bs.score) for bs in blendshapes}
        weighted = {
            emotion: sum(scores.get(name, 0.0) * weight for name, weight in table.items())
            for emotion, table in self.WEIGHTS.items()
        }
        emotion, confidence = max(weighted.items(), key=lambda pair: pair[1])
        if confidence < self.NEUTRAL_FLOOR:
            return "neutral", 0.2
        return emotion, confidence
