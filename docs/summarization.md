# Summarisation

`chronicler/core/llm/`, `chronicler/core/processing/summarizer.py`,
`chronicler/core/processing/handlers/summarizing.py`

## One provider interface

Everything reaches a model through `LlmClient`, which has two implementations:

| Provider | Reaches | Needs |
| -------- | ------- | ----- |
| `openai_compatible` | llama.cpp-server, Ollama, LM Studio, vLLM, hosted gateways | nothing — `httpx` is already a dependency |
| `llama_cpp` | an in-process `.gguf` file | the optional `llm` extra, imported lazily |

The OpenAI chat-completions API is the one thing every local runner and every hosted
gateway agrees on, so "local model" and "remote model" differ only by configuration.

## Model discovery

`ModelRegistry` fetches `GET /v1/models` and caches the result for five minutes.
Discovery is a network round trip and the picker is opened far more often than the set of
installed models changes, so the desktop app fetches once at startup
(`DesktopApp.refresh_models`) and the dialog opens instantly.

An unreachable listing endpoint is **not fatal**: the registry falls back to the
explicitly configured model, records `last_error`, and the picker still works. Plenty of
OpenAI-compatible servers do not implement `/models` at all.

## Two stages

Inherited from the prototype, which had the right shape:

```text
transcript → [chunk → bullet points] × n → recap
```

A transcript short enough to fit in one request skips the chunking entirely and goes
straight to a recap — one round trip instead of several.

`chunk_transcript` splits on **speaker turns**, never mid-turn. A single turn longer than
the budget becomes its own oversized chunk rather than being cut in half: losing speaker
attribution mid-sentence costs more than the overrun.

`budget_characters` reserves room for the prompt and the answer inside the context window
before deciding how much transcript fits. The prototype raised `OverflowError` when a
prompt exceeded the window; budgeting and splitting is the same insight without the dead
end.

## Numbered, not overwritten

Summaries accumulate. Each run adds a numbered row rather than replacing the last one, so
the same transcript can be summarised with several models and the outputs compared side
by side. Each row records the model, provider, the recap prompt used, chunk count and
token usage — which is what makes a comparison interpretable rather than just two blobs
of text.

Deleting one is explicit and confirmed.

## Prompts

Three templates, all in `SummarySettings` and all overridable per task:

* `system_prompt` — the standing instruction, plus a language request when one is set
* `chunk_prompt` — what to extract from one section
* `recap_prompt` — how to turn the notes into prose

Defaults live in settings and are editable in the settings panel. A per-task override
applies to that run only and is stored with the summary, so a summary always records the
instruction that produced it.

## State

A chronicle whose status is still `Imported`, `Transcribed` or `Cleaned` becomes
`Summarized`, and gains a `Summarized` tag. An explicitly-set status is never stomped —
the same rule transcription follows.

## `llm.model` is a default, not an address

`LlmSettings.is_configured` needs a base URL for a gateway, or a `model_path` for a local
`.gguf`. It deliberately does **not** need `llm.model`, and never needs an API key.

Both used to be required, and the result read as a contradiction: you configured a model,
were still told summaries were unavailable until the app was restarted, and then had to
pick a model in the dialog anyway. `llm.model` is what the summary dialog preselects —
including when discovery did not return it, so a model you have already named by hand
stays pickable against a gateway that does not implement `/models`. Plenty of local
gateways want no key at all, so demanding one only disabled a working setup.

The settings page shows only the fields the chosen provider reads: a gateway has no
`.gguf` file and a local model has no API key.

## Buttons that know whether a model exists

`SystemService.get_server_info()` reports `summarize` in its capabilities only when
`LlmSettings.is_configured`. The desktop reads it at startup, beside the model list, and
the generate action is disabled with "Configure an AI model to enable summaries" on hover
when it is absent.

It has to come from the server. In thin-client mode the client's own config is empty and
irrelevant; the model configuration that decides whether a summary can run is the
server's — which is why the settings page hides the language-model section entirely in
that mode rather than offering fields that would be saved and never read. See
[deployment-and-rpc.md](deployment-and-rpc.md).

### Changing the configuration does not need a restart

`SettingsView` calls back into `DesktopApp.on_llm_change()` after any `llm.*` change, and
that re-runs `refresh_models(refresh=True)` — a fresh model listing and a fresh reading of
the capabilities the views are built from.

The worker never needed this: it reads the same cached `Settings` object the settings page
edits, so a queued summary already used the new configuration. What did not update was the
interface, which read capabilities once at startup — so the button stayed greyed out until
the next launch even though the task behind it would have worked.

**Test connection** on the settings page is the same call, done deliberately, and reports
what came back: the model it reached, the reason it could not, or that the gateway
answered and listed nothing.

Unknown capabilities — the call failed — leaves the button enabled. A network hiccup
during startup should not quietly disable half the interface, and the task's own error
message is a better outcome than a button that refuses for the wrong reason.

`SummariesPanel.generate()` re-checks before queueing, so the action row and the panel's
own button behave identically and neither can queue a task that cannot run.

## Two token limits, and which is which

| Setting | What it does |
| ------- | ------------ |
| `llm.max_tokens` | The model's output cap. It reaches the API call. |
| `summary.chunk_token_budget` | How much room a chunk's answer is assumed to need when deciding how large a chunk may be. It never reaches the model. |

Both were called `max_tokens` and both defaulted to 1024, so raising the summary one
looked like it would let the model write more and actually only changed the chunking
arithmetic. The rename is the fix; there is no behaviour change.

## When the model list is empty

`ModelRegistry` records why discovery failed, and `SystemService.model_error` reports it.
The summary dialog shows it on the model field when the list came back empty — before
that, an unreachable gateway and a correctly-configured provider with no models looked
identical.
