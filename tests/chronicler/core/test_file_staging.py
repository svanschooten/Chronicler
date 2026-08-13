from pathlib import Path

from chronicler.core.file_staging import sanitize_stage_name, stage_local_file


def test_sanitize_stage_name_keeps_only_whitelisted_extension():
    name = sanitize_stage_name("my transcript.txt")
    assert name.endswith(".txt")
    assert "my transcript" not in name


def test_sanitize_stage_name_strips_traversal_and_separators():
    for evil in ("../../../etc/passwd", "..\\..\\windows\\system32\\config", "/etc/passwd"):
        name = sanitize_stage_name(evil)
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name


def test_sanitize_stage_name_handles_none_and_empty():
    assert sanitize_stage_name(None)
    assert sanitize_stage_name("")


def test_sanitize_stage_name_is_unique_per_call():
    assert sanitize_stage_name("a.txt") != sanitize_stage_name("a.txt")


def test_stage_local_file_copies_into_imports_dir(tmp_path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    source_file = source_dir / "transcript.txt"
    source_file.write_text("Alice: hello\n")

    staged = stage_local_file(source_file, imports_dir)

    assert staged.parent == imports_dir
    assert staged.name != "transcript.txt"
    assert staged.suffix == ".txt"
    assert staged.read_text() == "Alice: hello\n"
    # Original file is untouched, not moved.
    assert source_file.exists()


def test_stage_local_file_two_files_same_name_no_collision(tmp_path):
    source_dir = tmp_path / "Downloads"
    source_dir.mkdir()
    imports_dir = tmp_path / "workspace" / "imports"
    imports_dir.mkdir(parents=True)

    file_a = source_dir / "transcript.txt"
    file_a.write_text("first")
    staged_a = stage_local_file(file_a, imports_dir)

    file_a.write_text("second")  # simulate picking a different file with the same name
    staged_b = stage_local_file(file_a, imports_dir)

    assert staged_a != staged_b
    assert staged_a.read_text() == "first"
    assert staged_b.read_text() == "second"


def test_stage_local_file_result_is_relative_to_imports_dir(tmp_path):
    source_file = tmp_path / "weird..name.txt"
    source_file.write_text("data")
    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()

    staged = stage_local_file(source_file, imports_dir)

    assert Path(staged).resolve().is_relative_to(imports_dir.resolve())
