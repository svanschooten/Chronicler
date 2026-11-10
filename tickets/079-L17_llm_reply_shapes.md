# 079-L17_llm_reply_shapes

## Some model replies crash the summary or end up in it

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a failed summary with an unhelpful error, or reasoning text inside a saved summary. Change risk: very low. |
| reach | Summaries with reasoning models |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/core/llm/client.py`, `chronicler/core/processing/summarizer.py`, `tests/chronicler/core/llm/test_llm.py`, `docs/summarization.md` |

### description

Found in the review after wave 4.

- `OpenAiCompatibleClient.complete` reads `message.content` (`client.py:115`) and calls
  `.strip()` on it outside the `try` (`:121`). OpenAI-compatible servers return `null`
  content when a reasoning model spends its whole token budget thinking, and for some
  refusals. That raises a bare `AttributeError` instead of an `LlmError`. The
  `llama_cpp` path (`:184`) has the same shape.
- Reasoning models served by Ollama, llama.cpp and others put their reasoning in
  `<think>…</think>` at the start of `content`. The summarizer stores the text as it is,
  so the reasoning becomes part of every chunk note and of the saved summary.

### proposed fix

1. Treat missing or `null` content as an `LlmError` naming the `finish_reason`, so the
   message says to raise `llm.max_tokens` when it is `length`.
2. Strip a leading `<think>…</think>` block from completions before they are used.

Done when tests with a `null` content reply and a `<think>` reply produce a clear error
and a clean summary respectively.

### related tickets

- (RELATED) [050-L6_recap_budget](050-L6_recap_budget.md): the other summarizer robustness item
