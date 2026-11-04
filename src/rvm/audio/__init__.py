"""Audio capture and event analysis for the monitoring pipeline.

The video path in this project is a codec exercise; the audio path is not.
Audio exists here because a monitoring system that only sees cannot report a
glass break, a shout or an alarm -- the events that matter acoustically.

Two pieces, one thread each:

**AudioCapture** owns a PyAudio input stream and a daemon thread that pushes
fixed-size chunks into a bounded queue.  The queue is bounded on purpose: if
the analyser falls behind, dropping old audio is correct, because monitoring
audio is only useful while it is current.

**AudioAnalyzer** is pure signal processing -- RMS energy, zero-crossing rate
and spectral centroid.  No model, no download, ~1 ms per 64 ms chunk, which is
what makes it safe to run alongside the encoder.

Audio is analysed locally and never streamed.  Saying that plainly is more
honest than implying a full A/V pipeline exists.
"""

from .analysis import AudioAnalyzer, AudioEvent, EventType
from .capture import AudioCapture, AudioConfig

__all__ = [
    "AudioCapture",
    "AudioConfig",
    "AudioAnalyzer",
    "AudioEvent",
    "EventType",
]
