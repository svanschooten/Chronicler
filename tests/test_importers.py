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
    assert lines[1].text == "Hi Alice how are you?"


def test_default_importer():
    content = "Speaker One: Some text\nSpeaker Two: More text\n  continued"
    importer = DefaultImporter()
    lines = importer.parse(content)

    assert len(lines) == 2
    assert lines[0].speaker_name == "Speaker One"
    assert lines[0].text == "Some text"
    assert lines[1].speaker_name == "Speaker Two"
    assert lines[1].text == "More text continued"


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
