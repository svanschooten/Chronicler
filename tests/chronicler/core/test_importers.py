import pytest
from chronicler.core.processing.importers import DefaultImporter
from chronicler.core.models import TranscriptLine

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
    assert lines[0].text == "Hello world how are you?"
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
    assert lines[2].text == "nice okay I am the sound"
