# 052-L8_model_lifetimes

## Local models reload too often or are never released

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: wasted time and memory. Change risk: low. |
| reach | Local GGUF users, and anyone switching Whisper models |
| effort | S |
| evidence | read in code |
| touches | `chronicler/core/llm/client.py`, `chronicler/core/processing/handlers/summarizing.py`, `chronicler/core/processing/transcriber.py` |

### description

`handle_summarize` calls `build_client` per task (`summarizing.py:50`), so a local GGUF
model reloads for every summary. Whisper models stay in `_model_cache` forever with no
eviction (`transcriber.py:15`), so trying several sizes keeps them all in memory.

### proposed fix

Cache the llama.cpp client by model path and context size. Keep only the most recently
used Whisper model.

Done when two summaries load the model once, and switching Whisper size frees the previous
model.

### related tickets

- none
