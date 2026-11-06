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


def test_a_rejected_key_fails_at_once_rather_than_waiting_out_the_timeout(monkeypatch):
    """A 403 will not turn into an answer by asking again."""
    started = time.monotonic()
    real_ping = smoke.ping

    def wrong_key(port, _api_key):
        return real_ping(port, "not-the-key")

    monkeypatch.setattr(smoke, "ping", wrong_key)
    with pytest.raises(SystemExit, match="HTTP 403"):
        smoke.ping_server(SOURCE, timeout=60)

    assert time.monotonic() - started < 30


def test_an_answer_that_is_not_json_is_reported_as_it_is(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"<html>proxy error</html>"

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(smoke.urllib.request, "build_opener", lambda *_: Opener())

    assert smoke.ping(1, "key") == "<html>proxy error</html>"
