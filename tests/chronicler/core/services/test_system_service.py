"""Tests for the server-identity service a client uses to decide what to offer."""

import threading
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
    async def test_capabilities_are_checked_off_the_event_loop(self, settings):
        loop_thread = threading.get_ident()
        checked_on = []

        def record(_settings):
            checked_on.append(threading.get_ident())
            return {"transcribe"}

        with patch("chronicler.core.services.system_service.capabilities_for", record):
            info = await SystemService(settings=settings).get_server_info()

        assert checked_on and checked_on[0] != loop_thread
        assert info.capabilities == ["transcribe"]

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


class TestListModels:
    @pytest.mark.asyncio
    async def test_an_unreachable_gateway_reports_the_same_error_locally_and_remotely(
        self, settings
    ):
        from httpx import ASGITransport, AsyncClient

        from chronicler.core.container import Container
        from chronicler.core.remote import RemoteContainer
        from chronicler.core.rpc import RpcServer

        settings.llm.provider = "openai_compatible"
        settings.llm.base_url = "http://127.0.0.1:9/v1"
        settings.llm.model = "qwen3"
        local = SystemService(settings=settings)
        container = Container()
        container.register_instance(SystemService, local)
        app = RpcServer(container, services=[SystemService], api_key="k").build()

        local_check = await local.list_models()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            remote = RemoteContainer("http://t", client=client, api_key="k").resolve(SystemService)
            remote_check = await remote.list_models()

        assert local_check.error is not None
        assert remote_check == local_check
        assert remote_check.models == ["qwen3"]
