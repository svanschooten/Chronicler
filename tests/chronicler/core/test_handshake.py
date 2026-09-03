import logging
from unittest.mock import AsyncMock

import pytest

from chronicler import __version__
from chronicler.core.handshake import (
    HandshakeError,
    ServerUnreachableError,
    VersionMismatchError,
    perform_handshake,
    versions_compatible,
)
from chronicler.core.models import Chronicle, ServerInfo


def _resolver(info=None, chronicles=None, info_error=None):
    system = AsyncMock()
    if info_error is not None:
        system.get_server_info.side_effect = info_error
    else:
        system.get_server_info.return_value = info or ServerInfo(version=__version__)

    chronicle = AsyncMock()
    chronicle.list_chronicles.return_value = chronicles if chronicles is not None else []

    resolver = AsyncMock()

    def resolve(cls):
        return system if cls.__name__ == "SystemService" else chronicle

    resolver.resolve = resolve
    return resolver, system, chronicle


class TestVersionsCompatible:
    def test_identical_versions_match(self):
        assert versions_compatible("1.2.3", "1.2.3") is True

    def test_different_versions_do_not_match(self):
        assert versions_compatible("1.2.3", "1.2.4") is False

    def test_comparison_ignores_surrounding_whitespace(self):
        assert versions_compatible(" 1.2.3 ", "1.2.3") is True

    def test_a_missing_version_never_matches(self):
        assert versions_compatible("", "1.2.3") is False


class TestPerformHandshake:
    @pytest.mark.asyncio
    async def test_returns_the_server_info_on_success(self):
        resolver, _, _ = _resolver()

        result = await perform_handshake(resolver)

        assert result.server_info.version == __version__

    @pytest.mark.asyncio
    async def test_pulls_the_chronicle_list(self):
        resolver, _, chronicle = _resolver(
            chronicles=[Chronicle(title="One"), Chronicle(title="Two")]
        )

        result = await perform_handshake(resolver)

        assert result.chronicle_count == 2
        chronicle.list_chronicles.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_version_mismatch_is_refused(self):
        resolver, _, _ = _resolver(info=ServerInfo(version="9.9.9"))

        with pytest.raises(VersionMismatchError) as excinfo:
            await perform_handshake(resolver)

        assert "9.9.9" in str(excinfo.value)
        assert __version__ in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_a_version_mismatch_can_be_downgraded_to_a_warning(self, caplog):
        resolver, _, _ = _resolver(info=ServerInfo(version="9.9.9"))

        with caplog.at_level(logging.WARNING):
            result = await perform_handshake(resolver, require_matching_version=False)

        assert result.version_matches is False
        assert any("version" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_reported_clearly(self):
        resolver, _, _ = _resolver(info_error=OSError("connection refused"))

        with pytest.raises(ServerUnreachableError) as excinfo:
            await perform_handshake(resolver)

        assert "connection refused" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_unreachable_and_mismatch_share_a_base_error(self):
        assert issubclass(ServerUnreachableError, HandshakeError)
        assert issubclass(VersionMismatchError, HandshakeError)

    @pytest.mark.asyncio
    async def test_a_failing_chronicle_list_does_not_fail_the_handshake(self, caplog):
        resolver, _, chronicle = _resolver()
        chronicle.list_chronicles.side_effect = RuntimeError("boom")

        with caplog.at_level(logging.WARNING):
            result = await perform_handshake(resolver)

        assert result.chronicle_count is None
        assert result.version_matches is True

    @pytest.mark.asyncio
    async def test_it_logs_a_connected_line_for_log_monitoring(self, caplog):
        resolver, _, _ = _resolver(info=ServerInfo(version=__version__, capabilities=["import"]))

        with caplog.at_level(logging.INFO):
            await perform_handshake(resolver)

        assert any("Connected to Chronicler server" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_capabilities_are_carried_through(self):
        resolver, _, _ = _resolver(
            info=ServerInfo(version=__version__, capabilities=["import", "transcribe"])
        )

        result = await perform_handshake(resolver)

        assert "transcribe" in result.server_info.capabilities
