# 050-L6_recap_budget

## The summary recap is not budgeted

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: a loud failure on very long transcripts, after paying for every chunk. Change risk: low. |
| reach | Summaries of very long transcripts |
| effort | S |
| evidence | computed from the defaults |
| touches | `chronicler/core/processing/summarizer.py`, `tests/chronicler/core/processing/handlers/test_summarizing.py` |

### description

Chunks are budgeted against the context window, but the recap prompt is not
(`summarizer.py:123-125`). At defaults, the worst case overflows after 6 chunks, about
165,000 characters. The example transcript is 108,000.

The failure then repeats twice, because the task retries.

### proposed fix

When the joined notes exceed the budget, split them and summarise again until they fit,
then write the recap.

Done when a test with a fake client that rejects oversized prompts completes.

### related tickets

- (RELATED) [022-M6_retry_backoff](022-M6_retry_backoff.md): per-type attempts limit repeated paid runs
