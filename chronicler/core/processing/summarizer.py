"""Two-stage transcript summarisation: extract per chunk, then write one recap."""

import logging
from dataclasses import dataclass, field

from chronicler.core.config_sections import SummarySettings
from chronicler.core.llm.client import LlmClient
from chronicler.core.models import TranscriptLine

logger = logging.getLogger(__name__)

CHARACTERS_PER_TOKEN = 4


@dataclass
class SummaryDraft:
    content: str
    chunk_count: int
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    chunk_summaries: list[str] = field(default_factory=list)


def transcript_text(lines: list[TranscriptLine]) -> str:
    return "\n".join(
        f"{line.speaker_name or 'Unknown'}: {line.text.strip()}"
        for line in lines
        if line.text.strip()
    )


def chunk_transcript(lines: list[TranscriptLine], max_characters: int) -> list[str]:
    """
    Splits on speaker turns, never mid-turn, keeping each chunk under `max_characters`.

    A single turn longer than the limit becomes its own oversized chunk rather than being
    cut in half - losing the speaker attribution mid-sentence costs more than the overrun.
    """
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        turn = f"{line.speaker_name or 'Unknown'}: {text}"

        if current and length + len(turn) + 1 > max_characters:
            chunks.append("\n".join(current))
            current, length = [], 0

        current.append(turn)
        length += len(turn) + 1

    if current:
        chunks.append("\n".join(current))
    return chunks


def budget_characters(settings: SummarySettings, context_window: int) -> int:
    """
    How much transcript fits in one request, leaving room for the prompt and the answer.

    The prototype raised OverflowError when a prompt exceeded the window; budgeting up
    front and splitting is the same insight without the dead end.
    """
    reserved = (
        settings.chunk_token_budget + len(settings.chunk_prompt) // CHARACTERS_PER_TOKEN + 256
    )
    usable = max(context_window - reserved, 256)
    return usable * CHARACTERS_PER_TOKEN


async def summarize_transcript(
    client: LlmClient,
    lines: list[TranscriptLine],
    settings: SummarySettings,
    context_window: int,
    model: str | None = None,
    language: str | None = None,
) -> SummaryDraft:
    """Summarises a transcript, chunking it when it does not fit in one request."""
    if not lines:
        raise ValueError("Cannot summarize an empty transcript")

    max_characters = budget_characters(settings, context_window)
    chunks = chunk_transcript(lines, max_characters)
    logger.info(f"Summarizing {len(lines)} lines in {len(chunks)} chunk(s)")

    system = settings.system_prompt
    if language:
        system = f"{system}\n\nWrite your answer in {language}."

    prompt_tokens = 0
    completion_tokens = 0
    used_model = model or "unknown"

    if len(chunks) == 1:
        completion = await client.complete(
            f"{settings.recap_prompt}\n\n{chunks[0]}", system=system, model=model
        )
        return SummaryDraft(
            content=completion.text,
            chunk_count=1,
            model=completion.model,
            prompt_tokens=completion.prompt_tokens or 0,
            completion_tokens=completion.completion_tokens or 0,
        )

    extracted = []
    for index, chunk in enumerate(chunks, start=1):
        logger.info(f"Extracting from chunk {index}/{len(chunks)}")
        completion = await client.complete(
            f"{settings.chunk_prompt}\n\n{chunk}", system=system, model=model
        )
        extracted.append(completion.text)
        prompt_tokens += completion.prompt_tokens or 0
        completion_tokens += completion.completion_tokens or 0
        used_model = completion.model

    recap = await client.complete(
        f"{settings.recap_prompt}\n\n" + "\n".join(extracted), system=system, model=model
    )
    prompt_tokens += recap.prompt_tokens or 0
    completion_tokens += recap.completion_tokens or 0

    return SummaryDraft(
        content=recap.text,
        chunk_count=len(chunks),
        model=recap.model or used_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        chunk_summaries=extracted,
    )
