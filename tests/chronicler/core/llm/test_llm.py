import httpx
import pytest

from chronicler.core.config_sections import LlmSettings, SummarySettings
from chronicler.core.llm import (
    LlmError,
    LlmNotConfiguredError,
    ModelInfo,
    OpenAiCompatibleClient,
    build_client,
    discover_models,
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


class TestDiscoverModels:
    @pytest.mark.asyncio
    async def test_an_unconfigured_provider_lists_nothing(self):
        check = await discover_models(LlmSettings())

        assert check.models == []
        assert check.reachable

    @pytest.mark.asyncio
    async def test_it_asks_the_provider_every_time(self, monkeypatch):
        calls = []

        class Stub:
            async def list_models(self):
                calls.append(1)
                return [ModelInfo(id="qwen3", provider="openai_compatible")]

        monkeypatch.setattr("chronicler.core.llm.registry.build_client", lambda _s: Stub())

        await discover_models(settings())
        check = await discover_models(settings())

        assert len(calls) == 2
        assert check.models == ["qwen3"]

    @pytest.mark.asyncio
    async def test_an_unreachable_provider_falls_back_to_the_configured_model(self, monkeypatch):
        class Stub:
            async def list_models(self):
                raise LlmError("connection refused")

        monkeypatch.setattr("chronicler.core.llm.registry.build_client", lambda _s: Stub())

        check = await discover_models(settings())

        assert check.models == ["qwen3"]
        assert "refused" in check.error
        assert not check.reachable


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

    class _WindowedClient:
        """
        Refuses a request that does not fit the context window, the way a server does: the
        prompt and system prompt, at four characters a token, plus room for the answer.
        Chunk and condensing prompts get notes of `note_length`, the recap gets "recap".
        """

        def __init__(self, settings, context_window, note_length):
            self.settings = settings
            self.context_window = context_window
            self.note_length = note_length
            self.prompts = []

        async def list_models(self):
            return []

        async def complete(self, prompt, system=None, model=None, **options):
            from chronicler.core.llm import Completion

            tokens = (len(prompt) + len(system or "")) // 4 + self.settings.chunk_token_budget
            if tokens > self.context_window:
                raise LlmError(f"{tokens} tokens do not fit {self.context_window}")
            self.prompts.append(prompt)
            if prompt.startswith(self.settings.recap_prompt):
                return Completion(text="recap", model="stub")
            return Completion(text="n" * self.note_length, model="stub")

    @pytest.mark.asyncio
    async def test_notes_too_long_for_one_recap_are_condensed_first(self):
        from chronicler.core.processing.summarizer import budget_characters

        settings = SummarySettings()
        condense_budget = budget_characters(settings, 2048, settings.condense_prompt)
        # Three notes fit one condensing request, so every pass makes progress, but the
        # first set of notes is far too long for one recap.
        client = self._WindowedClient(settings, 2048, note_length=condense_budget // 3)
        lines = [line("x" * 200) for _ in range(60)]

        draft = await summarize_transcript(client, lines, settings, context_window=2048)

        assert draft.content == "recap"
        assert client.prompts[-1].startswith(settings.recap_prompt)
        condensing = [p for p in client.prompts if p.startswith(settings.condense_prompt)]
        assert condensing
        assert len(draft.chunk_summaries) == draft.chunk_count

    @pytest.mark.asyncio
    async def test_a_long_recap_prompt_is_budgeted(self):
        """
        Chunks were sized for the chunk prompt only, so a transcript that fit one chunk went
        out with a longer recap prompt and overflowed.
        """
        settings = SummarySettings(recap_prompt="Write a recap. " + "Be thorough. " * 230)
        client = self._WindowedClient(settings, 4096, note_length=40)
        lines = [line("x" * 200) for _ in range(50)]

        draft = await summarize_transcript(client, lines, settings, context_window=4096)

        assert draft.content == "recap"
        assert draft.chunk_count > 1

    @pytest.mark.asyncio
    async def test_notes_that_cannot_be_condensed_are_refused_before_the_recap(self):
        from chronicler.core.processing.summarizer import budget_characters

        settings = SummarySettings()
        condense_budget = budget_characters(settings, 2048, settings.condense_prompt)
        # No two notes fit one condensing request, so no pass could make progress.
        client = self._WindowedClient(settings, 2048, note_length=condense_budget // 2 + 10)
        lines = [line("x" * 200) for _ in range(60)]

        with pytest.raises(LlmError, match="Raise llm.context_window"):
            await summarize_transcript(client, lines, settings, context_window=2048)

        assert not any(p.startswith(settings.recap_prompt) for p in client.prompts)

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
