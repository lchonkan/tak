"""Tests for the pure DSP helpers in tak.core.audio."""

import numpy as np
import pytest

from tak.core.audio import BaseAudioRecorder, _resample


class TestResample:
    def test_same_rate_returns_input_unchanged(self):
        audio = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        out = _resample(audio, 16000, 16000)
        assert out is audio

    def test_downsample_length_matches_duration(self):
        # 1 second at 48 kHz -> exactly 16000 samples at 16 kHz.
        audio = np.zeros(48000, dtype=np.float32)
        out = _resample(audio, 48000, 16000)
        assert len(out) == 16000

    def test_upsample_length_matches_duration(self):
        # 1 second at 16 kHz -> 48000 samples at 48 kHz.
        audio = np.zeros(16000, dtype=np.float32)
        out = _resample(audio, 16000, 48000)
        assert len(out) == 48000

    def test_output_is_float32(self):
        audio = np.ones(44100, dtype=np.float64)
        out = _resample(audio, 44100, 16000)
        assert out.dtype == np.float32

    def test_endpoints_are_preserved(self):
        audio = np.linspace(-1.0, 1.0, 48000, dtype=np.float32)
        out = _resample(audio, 48000, 16000)
        # np.interp pins the first/last sample to the source endpoints.
        assert out[0] == pytest.approx(audio[0])
        assert out[-1] == pytest.approx(audio[-1])

    @pytest.mark.parametrize(
        "orig_sr,target_sr,n",
        [(48000, 16000, 48000), (44100, 16000, 44100), (16000, 48000, 16000)],
    )
    def test_length_formula_holds(self, orig_sr, target_sr, n):
        audio = np.zeros(n, dtype=np.float32)
        out = _resample(audio, orig_sr, target_sr)
        expected = int((n / orig_sr) * target_sr)
        assert len(out) == expected


class TestNormalize:
    def test_silence_is_left_untouched(self):
        audio = np.zeros(1000, dtype=np.float32)
        out = BaseAudioRecorder.normalize(audio)
        assert np.array_equal(out, audio)

    def test_near_silence_below_threshold_untouched(self):
        # peak just under the 1e-6 guard must not be amplified.
        audio = np.full(100, 5e-7, dtype=np.float32)
        out = BaseAudioRecorder.normalize(audio)
        assert np.array_equal(out, audio)

    def test_quiet_audio_is_boosted_toward_target_peak(self):
        audio = np.full(100, 0.1, dtype=np.float32)  # gain = min(9, 200) = 9
        out = BaseAudioRecorder.normalize(audio)
        assert np.max(np.abs(out)) == pytest.approx(0.9, rel=1e-3)

    def test_gain_is_capped_at_200x(self):
        audio = np.full(100, 0.001, dtype=np.float32)  # 0.9/0.001 = 900 -> capped
        out = BaseAudioRecorder.normalize(audio)
        assert np.max(np.abs(out)) == pytest.approx(0.2, rel=1e-3)

    def test_loud_audio_is_not_amplified_past_peak(self):
        audio = np.full(100, 0.9, dtype=np.float32)  # gain = 1.0, no boost
        out = BaseAudioRecorder.normalize(audio)
        assert np.max(np.abs(out)) == pytest.approx(0.9, rel=1e-3)
