# 047-L3_finish_translation

## 17 interface strings bypass translation

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: English text in a Dutch or German interface. Change risk: very low. |
| reach | Dutch and German users |
| effort | S |
| evidence | scanned |
| touches | `chronicler/desktop/views/tasks.py`, `chronicler/desktop/views/transcript/export.py`, `chronicler/desktop/imports.py`, `chronicler/desktop/dialogs.py`, `chronicler/core/extras.py`, `chronicler/i18n/messages/`, `tests/chronicler/i18n/test_no_bare_strings.py` |

### description

`TODO.md` calls the interface fully translated, but the guard only checks literals in a
few positions. It misses `show_snackbar(...)`, f-strings, `dialog_title=` and returned
messages:

- `views/tasks.py:95,116,138,143,145,147`
- `views/transcript/export.py:83,88,92,106,109`
- `desktop/imports.py:53,58,78,88,115` (line 88 holds two)
- Default labels in `dialogs.py:68,74,83,95`, and `purpose` and `note` in `core/extras.py`

### proposed fix

Move the strings to the catalogues in all three languages, and extend the guard to
`show_snackbar`, f-strings and `dialog_title`.

Done when the extended guard passes.

### related tickets

- none
