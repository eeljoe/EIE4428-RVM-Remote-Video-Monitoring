"""Face identification and facial-expression analysis.

Both stages ride on the same MediaPipe FaceLandmarker model: it returns 478
facial landmarks per face and, when asked, a set of ARKit-style blendshape
scores.  Landmarks give a geometric embedding for "who is this"; blendshapes
give mouth/brow/eye activations for "what does the face look like".

Two things this module deliberately does *not* do.

**It does not train anything.**  Identification compares a landmark-derived
embedding against a small in-memory database.  With an empty database the
honest report is "faces seen, none of them known" -- which is a different
statement from "recognition unavailable", and the two are reported as different
states so the dashboard cannot blur them.

**It does not run per frame.**  One FaceLandmarker call costs tens of
milliseconds; the session calls it on a cadence (see
:class:`rvm.server.session.StreamSession`), not on every picture, because the
video pipeline is the thing being graded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .models import model_path

__all__ = [
    "FaceRecognition",
    "FaceRecognizer",
    "EmotionDetection",
    "EmotionRecognizer",
]

log = logging.getLogger(__name__)

# Reported in place of a detector name when there is nothing to report.
STATE_DISABLED = "disabled"
STATE_UNAVAILABLE = "unavailable"
STATE_ERROR = "error"
STATE_NO_FACES = "no-faces"
STATE_NO_KNOWN = "no-known-faces"
STATE_RUNNING = "mediapipe"


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
    recognizer_name: str = STATE_DISABLED

    @property
    def count(self) -> int:
        return len(self.identities)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "identities": [
                {"name": name, "confidence": round(conf, 3), "bbox": list(bbox)}
                for name, conf, bbox in self.identities
            ],
            "recognizer": self.recognizer_name,
        }


@dataclass
class EmotionDetection:
    """Classified expressions with confidence scores."""

    emotions: List[Tuple[str, float, Tuple[int, int, int, int]]] = field(
        default_factory=list
    )  # (emotion, confidence, (x, y, w, h))
    detector_name: str = STATE_DISABLED

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
            "detector": self.detector_name,
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
        """Register a face by its landmark embedding."""
        self.known_faces[name] = np.asarray(embedding, dtype=np.float64)

    def remove_known_face(self, name: str) -> bool:
        """Forget a registered face; returns whether it was there."""
        return self.known_faces.pop(name, None) is not None

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
            return FaceRecognition([], STATE_NO_FACES)
        if not self.known_faces:
            return FaceRecognition([], STATE_NO_KNOWN)

        height, width = frame.shape[:2]
        identities = []
        for face_landmarks in result.face_landmarks:
            embedding = self._embedding(face_landmarks)
            if embedding is None:
                continue
            name, distance = self._nearest(embedding)
            confidence = max(0.0, 1.0 - distance)
            if name is not None and confidence >= self.threshold:
                identities.append(
                    (name, confidence, _boxes_from_landmarks(face_landmarks, width, height))
                )
        return FaceRecognition(identities, STATE_RUNNING)

    def _nearest(self, embedding: np.ndarray) -> tuple[str | None, float]:
        best_name = None
        best_distance = float("inf")
        for name, known in self.known_faces.items():
            distance = float(np.linalg.norm(embedding - known))
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
