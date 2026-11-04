"""Audio event detection from cheap signal features.

Three features carry all the discrimination here:

``rms``
    How loud the chunk is.  Separates silence from sound and loud from normal.
``zcr``
    Zero-crossing rate.  Speech and noise cross zero far more often than a
    sustained tone; combined with energy it is the classic voiced/unvoiced cue.
``centroid``
    Spectral centroid, i.e. how bright the chunk is.  A glass break is bright;
    an alarm is not.

The classifier is a small rule table over those three numbers.  It is easy to
argue that a learned model would do better -- it probably would -- but a rule
table is auditable, has no download, and costs about a millisecond per chunk,
which is the property that matters when it runs next to the encoder.

One deliberate behaviour: a quiet chunk produces **no event**.  The first
version reported an "ambient" event for every chunk, which at 15 chunks per
second floods the event list and hides the events worth seeing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np

__all__ = ["EventType", "AudioEvent", "AudioAnalyzer"]


class EventType(str, Enum):
    """Types of audio event."""

    LOUD_SOUND = "loud_sound"
    SPEECH = "speech"
    SILENCE = "silence"
    GUNSHOT = "gunshot"
    GLASS_BREAK = "glass_break"
    ALARM = "alarm"


@dataclass
class AudioEvent:
    """One detected audio event."""

    event_type: EventType
    confidence: float
    timestamp: float  # seconds since the analyser started
    duration: float  # seconds of audio this event covers
    energy: float  # RMS energy, 0-1
    metadata: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "type": self.event_type.value,
            "confidence": round(self.confidence, 3),
            "timestamp": round(self.timestamp, 3),
            "duration": round(self.duration, 3),
            "energy": round(self.energy, 3),
            **self.metadata,
        }


class AudioAnalyzer:
    """Rule-based acoustic event detector."""

    #: Loud chunks need this much recent history before "alarm" is believable.
    ALARM_HISTORY = 5
    #: A chunk in the speech band only counts as speech after this many in a
    #: row.  A microphone's own noise floor sits in that band: on the demo
    #: laptop a quiet room produced a speech-shaped chunk every other frame,
    #: which is a stream of events describing nothing.  Two extra chunks
    #: (~130 ms) is long enough to separate "someone spoke" from "the room
    #: hums", and short enough not to miss a short word.
    SPEECH_CHUNKS = 3

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.02,
        silence_threshold: float = 0.005,
    ) -> None:
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_threshold = silence_threshold
        self._frame_count = 0
        self._history: List[float] = []
        self._max_history = 50
        self._speech_streak = 0

    def reset(self) -> None:
        """Forget the running history."""
        self._frame_count = 0
        self._history.clear()
        self._speech_streak = 0

    def analyze(self, audio_chunk: np.ndarray) -> List[AudioEvent]:
        """Return the events present in one chunk (usually none)."""
        if audio_chunk.size == 0:
            return []

        samples = self._normalise(audio_chunk)
        rms = self._compute_rms(samples)
        zcr = self._compute_zcr(samples)
        centroid = self._compute_spectral_centroid(samples)

        self._history.append(rms)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        timestamp = self._frame_count * len(audio_chunk) / self.sample_rate
        duration = len(audio_chunk) / self.sample_rate
        self._frame_count += 1

        if rms > self.energy_threshold:
            self._speech_streak = 0
            return [
                AudioEvent(
                    event_type=self._classify_loud(rms, zcr, centroid),
                    confidence=min(1.0, rms / (self.energy_threshold * 2)),
                    timestamp=timestamp,
                    duration=duration,
                    energy=rms,
                    metadata={"zcr": round(zcr, 4), "centroid_hz": round(centroid, 1)},
                )
            ]

        if rms < self.silence_threshold:
            self._speech_streak = 0
            # Silence only means something after activity: a room that was
            # never loud produces a silent chunk every frame, and reporting
            # each one is noise rather than monitoring.
            recent = self._history[-10:]
            if len(self._history) >= 10 and float(np.mean(recent)) > self.silence_threshold * 2:
                return [
                    AudioEvent(
                        event_type=EventType.SILENCE,
                        confidence=0.8,
                        timestamp=timestamp,
                        duration=duration,
                        energy=rms,
                    )
                ]
            return []

        if zcr > 0.05:
            self._speech_streak += 1
            if self._speech_streak >= self.SPEECH_CHUNKS:
                return [
                    AudioEvent(
                        event_type=EventType.SPEECH,
                        confidence=0.7,
                        timestamp=timestamp,
                        duration=duration,
                        energy=rms,
                        metadata={"zcr": round(zcr, 4)},
                    )
                ]
            return []

        self._speech_streak = 0
        return []

    @staticmethod
    def _normalise(audio_chunk: np.ndarray) -> np.ndarray:
        """Scale integer samples to ``[-1, 1]`` floats."""
        if audio_chunk.dtype == np.int16:
            return audio_chunk.astype(np.float32) / 32768.0
        if audio_chunk.dtype == np.int32:
            return audio_chunk.astype(np.float32) / 2147483648.0
        return audio_chunk.astype(np.float32)

    def _classify_loud(self, energy: float, zcr: float, centroid: float) -> EventType:
        """Name a loud chunk from its brightness, crossing rate and history."""
        # A gunshot is a very short, very bright, noisy transient far above the
        # floor.  The crossing-rate floor is what separates an impulse from a
        # sustained bright sound, which this 64 ms window cannot tell apart by
        # duration alone.
        if energy > self.energy_threshold * 3 and centroid > 2000 and zcr > 0.25:
            return EventType.GUNSHOT

        # Glass breaks are bright and noisy: high centroid and high zcr.
        if centroid > 3000 and zcr > 0.1:
            return EventType.GLASS_BREAK

        # An alarm sustains its level instead of spiking and decaying.
        if len(self._history) >= self.ALARM_HISTORY:
            recent = self._history[-self.ALARM_HISTORY :]
            if all(level > self.energy_threshold * 0.8 for level in recent):
                return EventType.ALARM

        return EventType.LOUD_SOUND

    @staticmethod
    def _compute_rms(audio: np.ndarray) -> float:
        """Root-mean-square level, 0-1 for normalised input."""
        return float(np.sqrt(np.mean(np.square(audio))))

    @staticmethod
    def _compute_zcr(audio: np.ndarray) -> float:
        """Fraction of adjacent sample pairs that change sign."""
        if audio.size < 2:
            return 0.0
        signs = np.sign(audio)
        signs[signs == 0] = -1
        return float(np.sum(np.abs(np.diff(signs))) / 2 / audio.size)

    def _compute_spectral_centroid(self, audio: np.ndarray) -> float:
        """Energy-weighted mean frequency in Hz."""
        try:
            spectrum = np.abs(np.fft.rfft(audio))
            total = float(np.sum(spectrum))
            if total < 1e-10:
                return 0.0
            frequencies = np.fft.rfftfreq(len(audio), 1.0 / self.sample_rate)
            return float(np.sum(frequencies * spectrum) / total)
        except Exception:  # noqa: BLE001 - degenerate input means "no brightness"
            return 0.0

    def set_thresholds(
        self,
        energy_threshold: Optional[float] = None,
        silence_threshold: Optional[float] = None,
    ) -> None:
        """Change the detection floors."""
        if energy_threshold is not None:
            self.energy_threshold = float(energy_threshold)
        if silence_threshold is not None:
            self.silence_threshold = float(silence_threshold)

    def get_status(self) -> dict:
        """Current thresholds and how much audio has been seen."""
        return {
            "sample_rate": self.sample_rate,
            "energy_threshold": self.energy_threshold,
            "silence_threshold": self.silence_threshold,
            "frames_analyzed": self._frame_count,
            "history_length": len(self._history),
        }
