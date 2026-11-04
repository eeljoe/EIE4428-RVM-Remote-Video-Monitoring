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


def test_capture_degrades_quietly_without_a_microphone():
    capture = AudioCapture()
    assert isinstance(capture.available, bool)
    if not capture.available:
        assert isinstance(capture.unavailable_reason, str)
    assert capture.start() in (True, False)


def test_stopping_and_clearing_an_idle_capture_does_not_raise():
    capture = AudioCapture()
    capture.stop()
    capture.clear_buffer()
    capture.close()


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


def test_speech_is_moderate_energy_with_a_high_crossing_rate():
    analyzer = AudioAnalyzer()
    events = analyzer.analyze(noise(amplitude=0.01))
    assert [event.event_type for event in events] == [EventType.SPEECH]


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
