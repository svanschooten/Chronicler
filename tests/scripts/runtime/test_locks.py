"""Tests for the embedded-runtime lock tooling and the locks it produced."""

import pytest

from scripts.runtime import locks
from scripts.runtime.pins import COMPONENTS, FLET_CLIENT_VERSION, PLATFORMS

UV_OUTPUT = """\
PyYAML==6.0.3 \\
    --hash=sha256:aaa \\
    --hash=sha256:bbb
    # via chronicler
hf_xet==1.6.0 \\
    --hash=sha256:ccc
    # via
    #   huggingface-hub
"""


class TestParsing:
    def test_a_block_is_the_pin_and_its_hashes(self):
        blocks = locks.parse_blocks(UV_OUTPUT)

        assert blocks["pyyaml"] == [
            "PyYAML==6.0.3",
            "--hash=sha256:aaa",
            "--hash=sha256:bbb",
        ]

    def test_names_are_normalized_so_spellings_match_across_locks(self):
        assert set(locks.parse_blocks(UV_OUTPUT)) == {"pyyaml", "hf-xet"}

    def test_via_comments_are_not_mistaken_for_hashes(self):
        assert locks.parse_blocks(UV_OUTPUT)["hf-xet"] == ["hf_xet==1.6.0", "--hash=sha256:ccc"]

    def test_rendering_round_trips(self):
        blocks = locks.parse_blocks(UV_OUTPUT)

        assert locks.parse_blocks(locks.render(blocks)) == blocks

    def test_rendering_is_sorted_and_pip_readable(self):
        rendered = locks.render(locks.parse_blocks(UV_OUTPUT))

        assert rendered.startswith("hf_xet==1.6.0 \\\n    --hash=sha256:ccc\n")
        assert rendered.endswith("--hash=sha256:bbb\n")

    def test_a_component_lock_leaves_out_what_the_base_provides(self):
        blocks = locks.parse_blocks(UV_OUTPUT)

        assert set(locks.without(blocks, {"pyyaml": []})) == {"hf-xet"}


class TestStaleness:
    def test_identical_locks_have_no_differences(self, tmp_path):
        (tmp_path / "base.lock").write_text("a==1\n")

        assert locks.differences(tmp_path, {"base.lock": "a==1\n"}) == []

    def test_a_changed_pin_is_reported(self, tmp_path):
        (tmp_path / "base.lock").write_text("a==1\n")

        changes = locks.differences(tmp_path, {"base.lock": "a==2\n"})

        assert "-a==1" in changes
        assert "+a==2" in changes

    def test_a_missing_lock_is_reported(self, tmp_path):
        assert locks.differences(tmp_path, {"base.lock": "a==1\n"})


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
class TestCommittedLocks:
    def blocks(self, platform: str, name: str) -> locks.Blocks:
        return locks.parse_blocks((locks.LOCKS_DIR / platform / name).read_text())

    def test_every_lock_is_committed(self, platform):
        for name in locks.lock_names():
            assert (locks.LOCKS_DIR / platform / name).is_file(), name

    def test_every_requirement_is_hash_pinned(self, platform):
        for name in locks.lock_names():
            for requirement, block in self.blocks(platform, name).items():
                assert len(block) > 1, f"{requirement} in {name} has no hash"

    def test_components_do_not_repeat_the_base(self, platform):
        base = self.blocks(platform, "base.lock")
        for component in COMPONENTS:
            shared = set(base) & set(self.blocks(platform, f"component-{component}.lock"))
            assert not shared, f"{component} repeats {shared}"

    def test_the_locked_flet_desktop_matches_the_client_the_build_ships(self, platform):
        (pin,) = self.blocks(platform, "base.lock")["flet-desktop"][:1]

        assert pin == f"flet-desktop=={FLET_CLIENT_VERSION}"

    def test_llama_cpp_is_not_a_component(self, platform):
        for name in locks.lock_names():
            assert "llama-cpp-python" not in self.blocks(platform, name)
