from chronicler.core.processing.importers import DefaultImporter, RegexImporter


def test_regex_importer_basic():
    content = "Alice: Hello world\nBob: Hi Alice\n  how are you?"
    regex = r"^([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, 1, 2)
    lines = importer.parse(content)

    assert len(lines) == 2
    assert lines[0].speaker_name == "Alice"
    assert lines[0].text == "Hello world"
    assert lines[1].speaker_name == "Bob"
    assert lines[1].text == "Hi Alice\nhow are you?"


def test_regex_importer_custom():
    content = "[INFO] User1: Login\n[INFO] User2: Logout"
    regex = r"^\[INFO\] ([A-Za-z0-9]+):\s*(.*)$"
    importer = RegexImporter(regex, 1, 2)
    lines = importer.parse(content)

    assert len(lines) == 2
    assert lines[0].speaker_name == "User1"
    assert lines[0].text == "Login"
    assert lines[1].speaker_name == "User2"
    assert lines[1].text == "Logout"


def test_default_importer():
    content = "Speaker One: Some text\nSpeaker Two: More text\n  continued"
    importer = DefaultImporter()
    lines = importer.parse(content)

    assert len(lines) == 2
    assert lines[0].speaker_name == "Speaker One"
    assert lines[0].text == "Some text"
    assert lines[1].speaker_name == "Speaker Two"
    assert lines[1].text == "More text\ncontinued"


def test_default_importer_simple():
    importer = DefaultImporter()
    content = """
Speaker 1 : Hello world
            how are you?
Speaker 2 : I am fine.
"""
    lines = importer.parse(content)
    assert len(lines) == 2
    assert lines[0].speaker_name == "Speaker 1"
    assert lines[0].text == "Hello world\nhow are you?"
    assert lines[1].speaker_name == "Speaker 2"
    assert lines[1].text == "I am fine."


def test_default_importer_example_snippet():
    importer = DefaultImporter()
    content = """
Maldal  : test
Mittus  : Hello.
GM      : nice
          okay
          I am the sound
"""
    lines = importer.parse(content)
    assert len(lines) == 3
    assert lines[0].speaker_name == "Maldal"
    assert lines[0].text == "test"
    assert lines[1].speaker_name == "Mittus"
    assert lines[1].text == "Hello."
    assert lines[2].speaker_name == "GM"
    assert lines[2].text == "nice\nokay\nI am the sound"


def test_regex_importer_with_timestamp_group_uses_real_seconds():
    content = "[00:00:05] Alice: Hello\n[00:00:12] Bob: Hi Alice"
    regex = r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, speaker_group=2, text_group=3, timestamp_group=1)
    lines = importer.parse(content)

    assert lines[0].start_time == 5.0
    assert lines[1].start_time == 12.0


def test_regex_importer_with_timestamp_group_derives_end_time_from_next_line():
    content = "[00:00:05] Alice: Hello\n[00:00:12] Bob: Hi Alice\n[00:00:20] Alice: Bye"
    regex = r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, speaker_group=2, text_group=3, timestamp_group=1)
    lines = importer.parse(content)

    assert lines[0].end_time == 12.0
    assert lines[1].end_time == 20.0
    assert lines[2].end_time == lines[2].start_time == 20.0


def test_regex_importer_without_timestamp_group_still_uses_synthetic_index():
    """
    No timestamp_group given (the default) - behavior must be unchanged from before
    timestamped import existed: sequential per-line indices, not real timestamps.
    """
    content = "Alice: Hello\nBob: Hi Alice"
    regex = r"^([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, speaker_group=1, text_group=2)
    lines = importer.parse(content)

    assert lines[0].start_time == 0.0
    assert lines[1].start_time == 1.0


def test_regex_importer_applies_start_offset_to_synthetic_indices():
    """Appending to an existing transcript needs the new lines ordered after it."""
    content = "Alice: Hello\nBob: Hi Alice"
    regex = r"^([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, speaker_group=1, text_group=2)
    lines = importer.parse(content, start_offset=10.0)

    assert [line.start_time for line in lines] == [10.0, 11.0]
    assert [line.end_time for line in lines] == [11.0, 12.0]


def test_regex_importer_applies_start_offset_to_real_timestamps():
    content = "[00:00:05] Alice: Hello\n[00:00:12] Bob: Hi Alice"
    regex = r"^\[(\d\d:\d\d:\d\d)\] ([A-Za-z]+):\s*(.*)$"
    importer = RegexImporter(regex, speaker_group=2, text_group=3, timestamp_group=1)
    lines = importer.parse(content, start_offset=100.0)

    assert [line.start_time for line in lines] == [105.0, 112.0]
    assert [line.end_time for line in lines] == [112.0, 112.0]


def test_regex_importer_start_offset_defaults_to_zero():
    content = "Alice: Hello\nBob: Hi Alice"
    importer = DefaultImporter()
    assert [line.start_time for line in importer.parse(content)] == [0.0, 1.0]
