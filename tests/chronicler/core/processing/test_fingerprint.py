import pytest

from chronicler.core.processing.fingerprint import SAMPLE_BYTES, fingerprint_file


@pytest.fixture
def audio(tmp_path):
    def _write(name, content: bytes):
        path = tmp_path / name
        path.write_bytes(content)
        return path

    return _write


class TestFingerprintFile:
    def test_identical_content_fingerprints_identically(self, audio):
        first = audio("a.wav", b"x" * 1000)
        second = audio("b.wav", b"x" * 1000)

        assert fingerprint_file(first) == fingerprint_file(second)

    def test_different_content_fingerprints_differently(self, audio):
        first = audio("a.wav", b"x" * 1000)
        second = audio("b.wav", b"y" * 1000)

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_a_size_change_alone_changes_the_fingerprint(self, audio):
        first = audio("a.wav", b"x" * 1000)
        second = audio("b.wav", b"x" * 1001)

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_a_change_in_the_head_is_detected(self, audio):
        first = audio("a.wav", b"A" + b"x" * 999)
        second = audio("b.wav", b"B" + b"x" * 999)

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_a_change_in_the_tail_is_detected(self, audio):
        first = audio("a.wav", b"x" * 999 + b"A")
        second = audio("b.wav", b"x" * 999 + b"B")

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_a_change_in_the_head_of_a_large_file_is_detected(self, audio):
        body = b"x" * (SAMPLE_BYTES * 4)
        first = audio("a.wav", b"A" + body)
        second = audio("b.wav", b"B" + body)

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_a_change_in_the_tail_of_a_large_file_is_detected(self, audio):
        body = b"x" * (SAMPLE_BYTES * 4)
        first = audio("a.wav", body + b"A")
        second = audio("b.wav", body + b"B")

        assert fingerprint_file(first) != fingerprint_file(second)

    def test_the_filename_does_not_affect_the_fingerprint(self, audio):
        first = audio("recording.wav", b"same")
        second = audio("totally-different-name.mp3", b"same")

        assert fingerprint_file(first) == fingerprint_file(second)

    def test_an_empty_file_fingerprints_without_error(self, audio):
        assert fingerprint_file(audio("empty.wav", b""))

    def test_it_is_stable_across_calls(self, audio):
        path = audio("a.wav", b"stable")

        assert fingerprint_file(path) == fingerprint_file(path)

    def test_a_missing_file_raises(self, tmp_path):
        with pytest.raises(OSError):
            fingerprint_file(tmp_path / "nope.wav")
