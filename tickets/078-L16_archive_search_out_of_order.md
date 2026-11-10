# 078-L16_archive_search_out_of_order

## Archive search can show results for an earlier query

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: the list can disagree with the search box. Change risk: very low. |
| reach | All modes, mostly thin clients |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/desktop/views/archive/view.py`, `tests/chronicler/desktop/views/archive/test_view.py` |

### description

Found in the review after wave 4.

`search_changed` (`archive/view.py:157-159`) queries on every keystroke, and
`load_chronicles` (`:161-173`) shows whichever result arrives. Typing `abc` sends three
queries. Over a network a slower answer for `a` can arrive last and replace the results
for `abc`. Each keystroke also costs a full query and rebuilds the list.

### proposed fix

Wait about 250 ms after the last keystroke before querying, and discard any result whose
query is no longer the box's current value.

Done when a test that resolves an earlier query after a later one still shows the later
query's results.

### related tickets

- (RELATED) [063-F1_full_text_search](063-F1_full_text_search.md): makes each query more expensive, so this matters more after it
