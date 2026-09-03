import math
import wave

import pytest

from chronicler.core.config_sections import NormalizationSettings

pytest.importorskip("av", reason="requires the 'normalization' extra", exc_type=ImportError)

from chronicler.core.processing.normalizer import (  # noqa: E402
    NORMALIZED_SUFFIX,
    NormalizationError,
    build_filter_description,
    normalize_audio,
    normalized_path_for,
)


def write_tone(path, seconds=1.0, amplitude=0.05, rate=16000):
    """A quiet sine tone, so normalisation has something real to raise."""
    frames = bytearray()
    for index in range(int(seconds * rate)):
        value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * index / rate))
        frames += int(value).to_bytes(2, "little", signed=True)

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


class TestNormalizedPath:
    def test_derives_a_sibling_of_the_source(self, tmp_path):
        result = normalized_path_for(tmp_path / "gm.mp3")

        assert result.parent == tmp_path
        assert result.name == f"gm{NORMALIZED_SUFFIX}"

    def test_the_original_extension_does_not_leak_into_the_output(self, tmp_path):
        assert normalized_path_for(tmp_path / "a.ogg").suffix == ".wav"

    def test_a_dotted_stem_is_preserved(self, tmp_path):
        assert normalized_path_for(tmp_path / "session.3.gm.flac").name.startswith("session.3.gm")


class TestFilterDescription:
    def test_loudnorm_carries_the_configured_targets(self):
        settings = NormalizationSettings(target_lufs=-16.0, true_peak=-2.0, loudness_range=9.0)

        chain = build_filter_description(settings)

        assert "loudnorm=I=-16.0:TP=-2.0:LRA=9.0" in chain

    def test_denoise_is_absent_by_default(self):
        assert "afftdn" not in build_filter_description(NormalizationSettings())

    def test_denoise_can_be_enabled(self):
        assert "afftdn" in build_filter_description(NormalizationSettings(denoise=True))

    def test_a_highpass_is_added_when_configured(self):
        chain = build_filter_description(NormalizationSettings(highpass_hz=80))

        assert "highpass=f=80" in chain

    def test_a_highpass_is_absent_by_default(self):
        assert "highpass" not in build_filter_description(NormalizationSettings())

    def test_the_chain_ends_by_resampling_for_whisper(self):
        chain = build_filter_description(NormalizationSettings())

        assert "aresample=16000" in chain
        assert "aformat=" in chain

    def test_measurement_pass_uses_print_format(self):
        chain = build_filter_description(NormalizationSettings(), measure_only=True)

        assert "print_format=json" in chain


class TestNormalizeAudio:
    def test_produces_a_new_file_and_leaves_the_source_untouched(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav")
        before = source.read_bytes()

        result = normalize_audio(source)

        assert result.output_path.exists()
        assert result.output_path != source
        assert source.read_bytes() == before

    def test_the_output_is_readable_audio(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav")

        result = normalize_audio(source)

        with wave.open(str(result.output_path), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getframerate() == 16000
            assert handle.getnframes() > 0

    def test_it_reports_loudness_before_and_after(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav")

        result = normalize_audio(source)

        assert result.loudness_before is not None
        assert result.loudness_after is not None

    def test_a_quiet_track_is_brought_closer_to_the_target(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav", amplitude=0.02)
        settings = NormalizationSettings(target_lufs=-18.0)

        result = normalize_audio(source, settings)

        assert result.loudness_after > result.loudness_before
        assert abs(result.loudness_after - settings.target_lufs) < 6.0

    def test_the_output_location_can_be_chosen(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav")
        destination = tmp_path / "custom.wav"

        result = normalize_audio(source, output_path=destination)

        assert result.output_path == destination
        assert destination.exists()

    def test_a_missing_source_raises(self, tmp_path):
        with pytest.raises(NormalizationError):
            normalize_audio(tmp_path / "nope.wav")

    def test_a_file_with_no_audio_stream_raises(self, tmp_path):
        source = tmp_path / "notaudio.wav"
        source.write_bytes(b"this is not audio at all")

        with pytest.raises(NormalizationError):
            normalize_audio(source)

    def test_rerunning_overwrites_rather_than_accumulating(self, tmp_path):
        source = write_tone(tmp_path / "gm.wav")

        normalize_audio(source)
        normalize_audio(source)

        outputs = [item for item in tmp_path.iterdir() if item.name.endswith(NORMALIZED_SUFFIX)]
        assert len(outputs) == 1
