"""
The smoke test's server step, run against this source install instead of a built binary.

A real server process on a real port: this is the check that tells a release whether
`server` works, so it is worth a few seconds here to know the check itself works. The
server gets its own --config and a scratch working directory, so the developer's real
configuration is never read. `isolated_config` is not used: it moves HOME, which hides a
user-site install of the dependencies from the child process.
"""

import sys
import time

import pytest

from scripts.runtime import smoke

SOURCE = [sys.executable, "-m", "chronicler"]


def test_a_server_started_from_source_answers_ping(capsys):
    smoke.ping_server(SOURCE)

    assert "server answered ping" in capsys.readouterr().out


def test_a_server_that_exits_fails_the_check_straight_away():
    """A build without the server component exits; the check must not wait out its timeout."""
    started = time.monotonic()

    with pytest.raises(SystemExit, match="did not answer"):
        smoke.ping_server([sys.executable, "-c", "raise SystemExit(1)"], timeout=60)

    assert time.monotonic() - started < 30


def test_nothing_listening_is_not_an_answer():
    assert smoke.ping(smoke.free_port(), "key") is None
