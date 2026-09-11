"""Tests for the server-identity service a client uses to decide what to offer."""

from unittest.mock import AsyncMock, patch

import pytest

from chronicler import __version__
from chronicler.core.config import Settings
from chronicler.core.services.system_service import SystemService, capabilities_for


@pytest.fixture
def settings(isolated_config):
    return Settings()


class TestCapabilities:
    def test_the_always_available_ones_are_always_there(self, settings):
        found = capabilities_for(settings)

        assert {"import", "clean", "export"} <= found

    def test_summarize_needs_a_configured_provider(self, settings):
        assert "summarize" not in capabilities_for(settings)

    def test_a_configured_openai_gateway_enables_summarize(self, settings):
        settings.llm.provider = "openai_compatible"
        settings.llm.base_url = "http://localhost:8080/v1"
        settings.llm.model = "qwen3"

        assert "summarize" in capabilities_for(settings)

    def test_a_gateway_with_no_default_model_still_enables_summarize(self, settings):
        """The model is chosen per summary; an address is all the server needs."""
        settings.llm.provider = "openai_compatible"
        settings.llm.base_url = "http://localhost:8080/v1"

        assert "summarize" in capabilities_for(settings)

    def test_a_gateway_with_no_address_does_not(self, settings):
        settings.llm.provider = "openai_compatible"
        settings.llm.model = "qwen3"

        assert "summarize" not in capabilities_for(settings)

    def test_a_local_gguf_model_enables_summarize(self, settings):
        settings.llm.provider = "llama_cpp"
        settings.llm.model_path = "/models/qwen3-q4.gguf"

        assert "summarize" in capabilities_for(settings)

    def test_transcribe_follows_the_extra(self, settings):
        with patch(
            "chronicler.core.services.system_service.extras.is_available",
            side_effect=lambda name: name == "transcription",
        ):
            found = capabilities_for(settings)

        assert "transcribe" in found
        assert "normalize" not in found

    def test_normalize_follows_its_own_extra(self, settings):
        with patch(
            "chronicler.core.services.system_service.extras.is_available",
            side_effect=lambda name: name == "normalization",
        ):
            found = capabilities_for(settings)

        assert "normalize" in found
        assert "transcribe" not in found


class TestServerInfo:
    @pytest.mark.asyncio
    async def test_it_reports_this_version_and_its_capabilities(self, settings):
        service = SystemService(settings=settings)

        info = await service.get_server_info()

        assert info.version == __version__
        assert "import" in info.capabilities
        assert info.capabilities == sorted(info.capabilities)

    @pytest.mark.asyncio
    async def test_it_counts_chronicles_when_it_can(self, settings):
        repository = AsyncMock()
        repository.get_all.return_value = [object(), object()]
        service = SystemService(chronicle_repository=repository, settings=settings)

        assert (await service.get_server_info()).chronicle_count == 2

    @pytest.mark.asyncio
    async def test_a_failing_count_does_not_take_the_handshake_down(self, settings):
        repository = AsyncMock()
        repository.get_all.side_effect = RuntimeError("database locked")
        service = SystemService(chronicle_repository=repository, settings=settings)

        info = await service.get_server_info()

        assert info.chronicle_count is None
        assert info.version == __version__

    @pytest.mark.asyncio
    async def test_ping_answers(self, settings):
        assert await SystemService(settings=settings).ping() == "ok"
