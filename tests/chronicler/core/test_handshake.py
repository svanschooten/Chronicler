import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from chronicler import __version__
from chronicler.core.handshake import HandshakeError, perform_handshake
from chronicler.core.models import ServerInfo
from chronicler.core.services import SystemService


def _resolver(info=None, info_error=None):
    system = AsyncMock()
    if info_error is not None:
        system.get_server_info.side_effect = info_error
    else:
        system.get_server_info.return_value = info or ServerInfo(version=__version__)

    resolver = MagicMock()
    resolver.resolve.side_effect = lambda cls: system if cls is SystemService else None
    return resolver


class TestPerformHandshake:
    @pytest.mark.asyncio
    async def test_returns_the_server_info_on_success(self):
        info = ServerInfo(version=__version__, chronicle_count=2, capabilities=["import"])

        assert await perform_handshake(_resolver(info)) == info

    @pytest.mark.asyncio
    async def test_asks_only_the_system_service(self):
        resolver = _resolver()

        await perform_handshake(resolver)

        resolver.resolve.assert_called_once_with(SystemService)

    @pytest.mark.asyncio
    async def test_a_version_mismatch_is_refused(self):
        with pytest.raises(HandshakeError) as excinfo:
            await perform_handshake(_resolver(ServerInfo(version="9.9.9")))

        assert "9.9.9" in str(excinfo.value)
        assert __version__ in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_a_missing_server_version_is_refused(self):
        with pytest.raises(HandshakeError):
            await perform_handshake(_resolver(ServerInfo(version="")))

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_in_the_version_is_ignored(self):
        info = ServerInfo(version=f" {__version__} ")

        assert await perform_handshake(_resolver(info)) == info

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_reported_clearly(self):
        with pytest.raises(HandshakeError) as excinfo:
            await perform_handshake(_resolver(info_error=OSError("connection refused")))

        assert "connection refused" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_it_logs_a_connected_line_for_log_monitoring(self, caplog):
        info = ServerInfo(version=__version__, chronicle_count=3, capabilities=["import"])

        with caplog.at_level(logging.INFO):
            await perform_handshake(_resolver(info))

        (line,) = [r.message for r in caplog.records if "Connected to Chronicler" in r.message]
        assert "chronicles: 3" in line
        assert "capabilities: import" in line

    @pytest.mark.asyncio
    async def test_an_unknown_count_is_logged_as_unknown(self, caplog):
        with caplog.at_level(logging.INFO):
            await perform_handshake(_resolver(ServerInfo(version=__version__)))

        assert any("chronicles: unknown" in record.message for record in caplog.records)
