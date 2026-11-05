# 038-P3_lazy_imports

## Slow imports that most runs never use

### info

| | |
| --- | --- |
| importance | low |
| danger level | Low: slower startup. Change risk: very low. |
| reach | Every launch, especially thin clients |
| effort | XS |
| evidence | measured |
| touches | `chronicler/core/services/transcript_service.py`, `chronicler/core/database_manager.py` |

### description

Importing the desktop entry point takes 2.3 s, of which `alembic` is 499 ms and `fpdf` 471
ms. Thin clients never migrate, and few sessions export a PDF.

### proposed fix

Import `format_pdf` inside `export_pdf`, and `alembic` inside `_run_alembic_upgrade`. Add
a test that runs a subprocess importing `chronicler.core.services` and asserts neither is
in `sys.modules`.

Done when startup improves by about 0.5 s for everyone and about 1 s for thin clients.

### related tickets

- none
