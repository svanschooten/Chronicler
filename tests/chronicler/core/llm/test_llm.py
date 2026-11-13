import asyncio

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
    @pytest.mark.parametrize(
        ("finish_reason", "match"),
        [("length", "Raise llm.max_tokens"), ("stop", "finish reason: stop")],
    )
    async def test_a_null_reply_is_an_llm_error(self, finish_reason, match):
        def handler(_request):
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": None}, "finish_reason": finish_reason}]},
            )

        with pytest.raises(LlmError, match=match):
            await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

    @pytest.mark.asyncio
    async def test_a_leading_think_block_is_dropped(self):
        def handler(_request):
            content = "<think>\nhmm, the user wants\na recap</think>\n\nA recap."
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        result = await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

        assert result.text == "A recap."

    @pytest.mark.asyncio
    async def test_a_reply_of_only_unfinished_reasoning_is_an_error(self):
        def handler(_request):
            body = {
                "choices": [
                    {"message": {"content": "<think>still going"}, "finish_reason": "length"}
                ]
            }
            return httpx.Response(200, json=body)

        with pytest.raises(LlmError, match="Raise llm.max_tokens"):
            await OpenAiCompatibleClient(settings(), stub_server(handler)).complete("x")

    @pytest.mark.asyncio
    async def test_a_missing_base_url_is_refused(self):
        client = OpenAiCompatibleClient(LlmSettings(provider="openai_compatible", model="m"))

        with pytest.raises(LlmNotConfiguredError):
            await client.complete("x")


class TestReasoningReplies:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("<think>\nhmm</think>\n\nA recap.", "A recap."),
            # The chat template opened the block, so only the closing tag is in the reply.
            ("the user wants a recap\n</think>\n\nA recap.", "A recap."),
            ("A recap that mentions <think> tags.", "A recap that mentions <think> tags."),
            ("A recap. <think>aside</think> More.", "A recap. <think>aside</think> More."),
        ],
    )
    def test_reasoning_before_the_answer_is_removed(self, content, expected):
        from chronicler.core.llm.client import reply_text

        assert reply_text(content, "stop") == expected

    @pytest.mark.asyncio
    async def test_the_local_model_gets_the_same_treatment(self, monkeypatch):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from chronicler.core.llm.client import LlamaCppClient

        model = MagicMock()
        monkeypatch.setitem(
            sys.modules, "llama_cpp", SimpleNamespace(Llama=MagicMock(return_value=model))
        )
        client = LlamaCppClient(LlmSettings(provider="llama_cpp", model_path="a.gguf"))

        model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "reasoning</think>A recap."}}]
        }
        assert (await client.complete("x")).text == "A recap."

        model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": None}, "finish_reason": "length"}]
        }
        with pytest.raises(LlmError, match="Raise llm.max_tokens"):
            await client.complete("x")

    @pytest.mark.asyncio
    async def test_a_summary_from_a_reasoning_model_holds_no_reasoning(self):
        def handler(_request):
            content = "<think>\nwhat matters here</think>\n\n- a point"
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        client = OpenAiCompatibleClient(settings(), stub_server(handler))
        lines = [line("x" * 200) for _ in range(20)]

        draft = await summarize_transcript(
            client, lines, SummarySettings(chunk_token_budget=64), context_window=256
        )

        assert draft.chunk_count > 1
        assert draft.content == "- a point"
        assert all(note == "- a point" for note in draft.chunk_summaries)


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


class TestLocalModelLifetime:
    @pytest.fixture(autouse=True)
    def _fresh(self, monkeypatch):
        from chronicler.core.llm import client as client_module

        monkeypatch.setattr(client_module, "_local_model", None)

    @staticmethod
    def _factory(monkeypatch):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        factory = MagicMock()
        monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(Llama=factory))
        return factory

    def _load(self, **overrides):
        from chronicler.core.llm.client import LlamaCppClient

        values = {"provider": "llama_cpp", "model_path": "a.gguf", "context_window": 4096}
        return LlamaCppClient(LlmSettings(**{**values, **overrides}))._load()

    def test_two_clients_load_the_model_once(self, monkeypatch):
        factory = self._factory(monkeypatch)
        first = self._load()
        second = self._load()

        assert first is second
        assert factory.call_count == 1

    def test_another_model_or_context_size_replaces_it(self, monkeypatch):
        factory = self._factory(monkeypatch)
        self._load()
        self._load(model_path="b.gguf")
        self._load(model_path="b.gguf", context_window=8192)

        assert factory.call_count == 3

    @pytest.mark.asyncio
    async def test_generations_never_overlap(self, monkeypatch):
        """llama.cpp is not thread-safe, and every client now shares one model."""
        import threading
        import time

        from chronicler.core.llm.client import LlamaCppClient

        state = {"running": 0, "most": 0}
        guard = threading.Lock()

        def generate(**_kwargs):
            with guard:
                state["running"] += 1
                state["most"] = max(state["most"], state["running"])
            time.sleep(0.05)
            with guard:
                state["running"] -= 1
            return {"choices": [{"message": {"content": "ok"}}]}

        factory = self._factory(monkeypatch)
        factory.return_value.create_chat_completion.side_effect = generate
        values = {"provider": "llama_cpp", "model_path": "a.gguf"}
        clients = [LlamaCppClient(LlmSettings(**values)) for _ in range(3)]

        await asyncio.gather(*(client.complete("x") for client in clients))

        assert state["most"] == 1
        assert factory.call_count == 1

    @pytest.mark.asyncio
    async def test_switching_away_from_the_local_model_frees_it(self, monkeypatch):
        from chronicler.core.llm import client as client_module

        self._factory(monkeypatch)
        self._load()
        build_client(settings())
        assert client_module._local_model is None

        self._load()
        await discover_models(LlmSettings())
        assert client_module._local_model is None

    def test_using_the_local_model_keeps_it(self, monkeypatch):
        from chronicler.core.llm import client as client_module

        self._factory(monkeypatch)
        self._load()
        build_client(LlmSettings(provider="llama_cpp", model_path="a.gguf", context_window=4096))

        assert client_module._local_model is not None
