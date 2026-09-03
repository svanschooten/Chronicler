import httpx
import pytest

from chronicler.core.config_sections import LlmSettings, SummarySettings
from chronicler.core.llm import (
    LlmError,
    LlmNotConfiguredError,
    ModelRegistry,
    OpenAiCompatibleClient,
    build_client,
)
from chronicler.core.models import TranscriptLine
from chronicler.core.processing.summarizer import (
    budget_characters,
    chunk_transcript,
    summarize_transcript,
    transcript_text,
)


def stub_server(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def settings(**overrides):
    base = {
        "provider": "openai_compatible",
        "base_url": "http://model:8080/v1",
        "model": "qwen3",
    }
    return LlmSettings(**{**base, **overrides})


def line(text, speaker="GM"):
    return TranscriptLine(speaker_name=speaker, text=text, start_time=0.0, end_time=1.0)


class TestBuildClient:
    def test_openai_compatible(self):
        assert isinstance(build_client(settings()), OpenAiCompatibleClient)

    def test_an_unconfigured_provider_raises(self):
        with pytest.raises(LlmNotConfiguredError):
            build_client(LlmSettings())


class TestOpenAiCompatibleClient:
    @pytest.mark.asyncio
    async def test_lists_models(self):
        def handler(request):
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": "qwen3"}, {"id": "llama3"}]})

        client = OpenAiCompatibleClient(settings(), stub_server(handler))

        assert [model.id for model in await client.list_models()] == ["qwen3", "llama3"]

    @pytest.mark.asyncio
    async def test_completes_a_prompt(self):
        def handler(request):
            assert request.url.path == "/v1/chat/completions"
            return httpx.Response(
                200,
                json={
                    "model": "qwen3",
                    "choices": [{"message": {"content": "  A recap.  "}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )

        client = OpenAiCompatibleClient(settings(), stub_server(handler))
        result = await client.complete("summarize this", system="be brief")

        assert result.text == "A recap."
        assert result.model == "qwen3"
        assert result.prompt_tokens == 10

    @pytest.mark.asyncio
    async def test_sends_the_system_prompt_first(self):
        captured = {}

        def handler(request):
            import json

            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        await OpenAiCompatibleClient(settings(), stub_server(handler)).complete(
            "user text", system="system text"
        )

        assert captured["messages"][0] == {"role": "system", "content": "system text"}
        assert captured["messages"][1]["content"] == "user text"

    @pytest.mark.asyncio
    async def test_sends_the_api_key_as_a_bearer_token(self):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        await OpenAiCompatibleClient(settings(api_key="secret"), stub_server(handler)).complete("x")

        assert captured["auth"] == "Bearer secret"

    @pytest.mark.asyncio
    async def test_an_http_error_is_wrapped(self):
        def handler(_request):
            return httpx.Response(500, text="upstream exploded")

        with pytest.raises(LlmError, match="500"):
            await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_wrapped(self):
        def handler(_request):
            raise httpx.ConnectError("refused")

        with pytest.raises(LlmError, match="Could not reach"):
            await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

    @pytest.mark.asyncio
    async def test_an_unexpected_shape_is_reported(self):
        def handler(_request):
            return httpx.Response(200, json={"nonsense": True})

        with pytest.raises(LlmError, match="Unexpected response"):
            await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

    @pytest.mark.asyncio
    async def test_a_missing_base_url_is_refused(self):
        client = OpenAiCompatibleClient(LlmSettings(provider="openai_compatible", model="m"))

        with pytest.raises(LlmNotConfiguredError):
            await client.complete("x")


class TestModelRegistry:
    @pytest.mark.asyncio
    async def test_an_unconfigured_provider_lists_nothing(self):
        assert await ModelRegistry(LlmSettings()).list_models() == []

    @pytest.mark.asyncio
    async def test_results_are_cached_between_calls(self, monkeypatch):
        calls = []

        class Stub:
            async def list_models(self):
                calls.append(1)
                from chronicler.core.llm import ModelInfo

                return [ModelInfo(id="qwen3", provider="openai_compatible")]

        monkeypatch.setattr("chronicler.core.llm.registry.build_client", lambda _s: Stub())
        registry = ModelRegistry(settings())

        await registry.list_models()
        await registry.list_models()

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_refresh_bypasses_the_cache(self, monkeypatch):
        calls = []

        class Stub:
            async def list_models(self):
                calls.append(1)
                return []

        monkeypatch.setattr("chronicler.core.llm.registry.build_client", lambda _s: Stub())
        registry = ModelRegistry(settings())

        await registry.list_models()
        await registry.list_models(refresh=True)

        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_an_unreachable_provider_falls_back_to_the_configured_model(self, monkeypatch):
        class Stub:
            async def list_models(self):
                raise LlmError("connection refused")

        monkeypatch.setattr("chronicler.core.llm.registry.build_client", lambda _s: Stub())
        registry = ModelRegistry(settings())

        assert await registry.model_ids() == ["qwen3"]
        assert "refused" in registry.last_error


class TestChunking:
    def test_a_short_transcript_is_one_chunk(self):
        assert len(chunk_transcript([line("a"), line("b")], 1000)) == 1

    def test_it_splits_on_turn_boundaries(self):
        lines = [line("x" * 40) for _ in range(5)]

        chunks = chunk_transcript(lines, 100)

        assert len(chunks) > 1
        assert all(chunk.startswith("GM:") for chunk in chunks)

    def test_a_single_oversized_turn_is_kept_whole(self):
        chunks = chunk_transcript([line("x" * 500)], 100)

        assert len(chunks) == 1
        assert "x" * 500 in chunks[0]

    def test_blank_lines_are_skipped(self):
        assert chunk_transcript([line("   "), line("real")], 1000) == ["GM: real"]

    def test_transcript_text_labels_every_speaker(self):
        text = transcript_text([line("hi", "Alice"), line("hello", "Bob")])

        assert text == "Alice: hi\nBob: hello"

    def test_the_budget_leaves_room_for_the_answer(self):
        budget = budget_characters(SummarySettings(max_tokens=1024), context_window=8192)

        assert 0 < budget < 8192 * 4

    def test_a_tiny_context_window_still_yields_a_usable_budget(self):
        assert budget_characters(SummarySettings(max_tokens=1024), context_window=512) > 0


class TestSummarizeTranscript:
    class _Client:
        def __init__(self, replies=None):
            self.prompts = []
            self.replies = replies or []

        async def list_models(self):
            return []

        async def complete(self, prompt, system=None, model=None, **options):
            from chronicler.core.llm import Completion

            self.prompts.append(prompt)
            text = self.replies[len(self.prompts) - 1] if self.replies else "a recap"
            return Completion(
                text=text, model=model or "stub", prompt_tokens=5, completion_tokens=3
            )

    @pytest.mark.asyncio
    async def test_a_short_transcript_takes_a_single_pass(self):
        client = self._Client()

        draft = await summarize_transcript(
            client, [line("hello")], SummarySettings(), context_window=8192
        )

        assert draft.chunk_count == 1
        assert len(client.prompts) == 1
        assert draft.content == "a recap"

    @pytest.mark.asyncio
    async def test_a_long_transcript_extracts_then_recaps(self):
        client = self._Client()
        lines = [line("x" * 200) for _ in range(20)]

        draft = await summarize_transcript(
            client, lines, SummarySettings(max_tokens=64), context_window=256
        )

        assert draft.chunk_count > 1
        assert len(client.prompts) == draft.chunk_count + 1
        assert draft.chunk_summaries

    @pytest.mark.asyncio
    async def test_token_usage_is_accumulated(self):
        client = self._Client()
        lines = [line("x" * 200) for _ in range(10)]

        draft = await summarize_transcript(
            client, lines, SummarySettings(max_tokens=64), context_window=256
        )

        assert draft.prompt_tokens >= 10

    @pytest.mark.asyncio
    async def test_the_language_is_requested_in_the_system_prompt(self):
        captured = {}

        class Recorder(self._Client):
            async def complete(self, prompt, system=None, model=None, **options):
                captured["system"] = system
                return await super().complete(prompt, system, model, **options)

        await summarize_transcript(
            Recorder(), [line("hi")], SummarySettings(), context_window=8192, language="nl"
        )

        assert "nl" in captured["system"]

    @pytest.mark.asyncio
    async def test_the_recap_prompt_is_used(self):
        client = self._Client()
        settings_with_prompt = SummarySettings(recap_prompt="CUSTOM RECAP INSTRUCTION")

        await summarize_transcript(client, [line("hi")], settings_with_prompt, context_window=8192)

        assert client.prompts[0].startswith("CUSTOM RECAP INSTRUCTION")

    @pytest.mark.asyncio
    async def test_an_empty_transcript_is_refused(self):
        with pytest.raises(ValueError):
            await summarize_transcript(self._Client(), [], SummarySettings(), context_window=8192)
