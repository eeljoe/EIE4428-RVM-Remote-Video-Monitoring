"""Audio capture surface and the acoustic event rules.

The analyser is arithmetic, so every branch can be driven to a known answer
with a synthetic chunk: a tone for loud-but-not-bright, noise for bright, and a
run of loud chunks followed by silence for the one event that needs history.
None of these tests need a microphone; the two that touch
:class:`~rvm.audio.capture.AudioCapture` only assert that a machine without one
degrades quietly.
"""

import numpy as np
import pytest

from rvm.audio import AudioAnalyzer, AudioCapture, AudioConfig, AudioEvent, EventType

SILENCE = np.zeros(1024, dtype=np.float32)


def tone(frequency: float, amplitude: float = 0.1, size: int = 1024) -> np.ndarray:
    """A pure tone at *frequency* Hz, which is loud but not bright."""
    t = np.arange(size) / 16000.0
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def noise(amplitude: float, size: int = 1024, seed: int = 7) -> np.ndarray:
    """Deterministic white noise, which is bright and busy."""
    rng = np.random.default_rng(seed)
    return (amplitude * rng.standard_normal(size)).astype(np.float32)


# --------------------------------------------------------------------------
# Configuration and capture
# --------------------------------------------------------------------------


def test_default_capture_configuration():
    config = AudioConfig()
    assert (config.sample_rate, config.channels, config.chunk_size) == (16000, 1, 1024)
    assert config.format == "int16"


def test_chunk_duration_follows_the_sample_rate():
    assert AudioConfig(sample_rate=16000, chunk_size=1600).chunk_duration_ms == pytest.approx(100.0)


def test_capture_starts_out_stopped():
    capture = AudioCapture()
    assert capture.running is False
    assert capture.read(timeout=0.01) is None


def test_capture_reports_unavailable_when_no_device_can_be_opened(monkeypatch):
    """No sound card: available is false, start refuses, nothing opens.

    The device probe is replaced so the test never touches real hardware -- a
    unit test that opens the microphone holds it for the life of the process.
    """
    capture = AudioCapture()
    monkeypatch.setattr(capture, "_probe_device", lambda: False)
    capture._available = None

    assert capture.available is False
    assert capture.start() is False
    assert capture.running is False
    capture.close()


class FakeStream:
    """A PortAudio stream whose device is gone the moment it is opened."""

    def __init__(self):
        self.closed = False

    def is_active(self):
        return False

    def read(self, size, exception_on_overflow=True):
        raise OSError("device gone")

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class FakePyAudio:
    def __init__(self, stream):
        self.stream = stream

    def open(self, **kwargs):
        return self.stream

    def get_default_input_device_info(self):
        return {"index": 0, "name": "fake"}

    def terminate(self):
        pass


def capture_with(stream):
    capture = AudioCapture()
    capture._pyaudio = FakePyAudio(stream)
    capture._available = True
    return capture


def test_start_does_not_leave_a_dead_capture_looking_alive():
    """Device opens and dies at once: the flag must not end up True.

    Driving this through start() rather than poking the loop directly is what
    makes it a regression test: the bug was the ordering of the flag and the
    thread start inside start().
    """
    capture = capture_with(FakeStream())

    assert capture.start() is True
    for _ in range(100):
        if capture._capture_thread is not None and not capture._capture_thread.is_alive():
            break
        time.sleep(0.01)

    assert capture._capture_thread is not None
    assert not capture._capture_thread.is_alive()
    assert capture.running is False
    assert capture.read() is None
    capture.stop()


def test_stop_releases_a_stream_that_died_on_its_own():
    """A dead loop leaves the stream open; stop() must close it anyway."""
    stream = FakeStream()
    capture = capture_with(stream)
    capture._stream = stream
    capture._running = False  # what the loop's finally leaves behind

    capture.stop()

    assert stream.closed is True


def test_stopping_and_clearing_an_idle_capture_does_not_raise():
    capture = AudioCapture()
    capture.stop()
    capture.clear_buffer()
    capture.close()
    assert capture.running is False


# --------------------------------------------------------------------------
# Event shapes
# --------------------------------------------------------------------------


def test_event_snapshot_is_json_friendly_and_keeps_metadata():
    event = AudioEvent(
        event_type=EventType.SPEECH,
        confidence=0.7,
        timestamp=2.0,
        duration=1.0,
        energy=0.15,
        metadata={"zcr": 0.08},
    )
    snapshot = event.snapshot()
    assert snapshot["type"] == "speech"
    assert snapshot["confidence"] == 0.7
    assert snapshot["zcr"] == 0.08


def test_every_event_type_has_a_stable_string():
    assert EventType.LOUD_SOUND.value == "loud_sound"
    assert EventType.GLASS_BREAK.value == "glass_break"
    assert EventType.ALARM.value == "alarm"


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------


def test_rms_of_a_constant_half_scale_signal_is_a_half():
    assert AudioAnalyzer._compute_rms(np.full(1000, 0.5, dtype=np.float32)) == pytest.approx(0.5)


def test_rms_of_digital_silence_is_zero():
    assert AudioAnalyzer._compute_rms(SILENCE) == 0.0


def test_a_constant_signal_never_crosses_zero():
    assert AudioAnalyzer._compute_zcr(np.ones(1000, dtype=np.float32)) == 0.0


def test_an_alternating_signal_crosses_zero_on_every_sample():
    assert AudioAnalyzer._compute_zcr(np.array([1, -1] * 500, dtype=np.float32)) == pytest.approx(0.999)


def test_the_spectral_centroid_of_a_kilohertz_tone_is_a_kilohertz():
    centroid = AudioAnalyzer(sample_rate=16000)._compute_spectral_centroid(tone(1000.0))
    assert 800 < centroid < 1200


def test_the_spectral_centroid_of_silence_is_zero():
    assert AudioAnalyzer()._compute_spectral_centroid(SILENCE) == 0.0


# --------------------------------------------------------------------------
# Event detection
# --------------------------------------------------------------------------


def test_an_empty_chunk_produces_no_event():
    assert AudioAnalyzer().analyze(np.array([], dtype=np.float32)) == []


def test_a_quiet_room_produces_no_event_rather_than_an_ambient_one():
    assert AudioAnalyzer().analyze(tone(1000.0, amplitude=0.0005)) == []


def test_a_loud_unremarkable_sound_is_a_loud_sound():
    events = AudioAnalyzer().analyze(tone(100.0, amplitude=0.1))
    assert [event.event_type for event in events] == [EventType.LOUD_SOUND]


def test_a_bright_signal_with_moderate_energy_is_a_glass_break():
    events = AudioAnalyzer().analyze(noise(amplitude=0.04))
    assert [event.event_type for event in events] == [EventType.GLASS_BREAK]


def test_a_very_bright_very_loud_transient_is_a_gunshot():
    events = AudioAnalyzer().analyze(noise(amplitude=0.5))
    assert [event.event_type for event in events] == [EventType.GUNSHOT]


def test_a_sustained_loud_level_becomes_an_alarm():
    analyzer = AudioAnalyzer()
    events = []
    for _ in range(AudioAnalyzer.ALARM_HISTORY):
        events = analyzer.analyze(tone(100.0, amplitude=0.1))
    assert [event.event_type for event in events] == [EventType.ALARM]


def test_silence_is_only_reported_after_activity():
    analyzer = AudioAnalyzer()
    for _ in range(10):
        analyzer.analyze(tone(100.0, amplitude=0.5))
    events = analyzer.analyze(SILENCE)
    assert [event.event_type for event in events] == [EventType.SILENCE]


def test_silence_on_its_own_says_nothing():
    analyzer = AudioAnalyzer()
    assert analyzer.analyze(SILENCE) == []


def test_speech_needs_a_few_chunks_in_a_row():
    """One speech-shaped chunk is a noisy room, not someone talking.

    The microphone's own noise floor sits in the speech band: without this
    rule a quiet room produced an event every other frame.
    """
    analyzer = AudioAnalyzer()
    chunk = noise(amplitude=0.01)

    assert analyzer.analyze(chunk) == []
    assert analyzer.analyze(chunk) == []
    assert [event.event_type for event in analyzer.analyze(chunk)] == [EventType.SPEECH]


def test_the_speech_streak_restarts_after_a_quiet_chunk():
    analyzer = AudioAnalyzer()
    analyzer.analyze(noise(amplitude=0.01))
    analyzer.analyze(noise(amplitude=0.01))
    analyzer.analyze(SILENCE)

    assert analyzer.analyze(noise(amplitude=0.01)) == []


def test_int16_samples_are_scaled_before_analysis():
    analyzer = AudioAnalyzer()
    events = analyzer.analyze(np.full(1024, 30000, dtype=np.int16))
    assert events and events[0].energy > analyzer.energy_threshold


# --------------------------------------------------------------------------
# Bookkeeping
# --------------------------------------------------------------------------


def test_thresholds_can_be_changed_after_construction():
    analyzer = AudioAnalyzer()
    analyzer.set_thresholds(energy_threshold=0.05, silence_threshold=0.02)
    assert (analyzer.energy_threshold, analyzer.silence_threshold) == (0.05, 0.02)


def test_status_counts_the_chunks_it_has_seen():
    analyzer = AudioAnalyzer(sample_rate=48000)
    for _ in range(3):
        analyzer.analyze(tone(100.0))
    status = analyzer.get_status()
    assert status["frames_analyzed"] == 3
    assert status["sample_rate"] == 48000


def test_reset_forgets_the_history():
    analyzer = AudioAnalyzer()
    analyzer.analyze(tone(100.0))
    analyzer.reset()
    status = analyzer.get_status()
    assert status["frames_analyzed"] == 0
    assert status["history_length"] == 0


def test_speech_is_reported_at_most_once_per_cooldown():
    """A room with the gain up makes speech-shaped audio continuously.

    The three-chunk rule stops the first event; without a cooldown the rest of
    the chunk stream becomes one event after another.  Twenty chunks yield
    three events: the streak completes at chunk 3, then the cooldown allows one
    every eight chunks (11, 19).
    """
    analyzer = AudioAnalyzer()
    chunk = noise(amplitude=0.01)

    reported_at = [
        frame for frame in range(1, 21) if analyzer.analyze(chunk)
    ]

    assert reported_at == [3, 11, 19]

