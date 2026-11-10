"""Ticket 038: slow imports most runs never use stay out of startup."""

import subprocess
import sys


def test_importing_the_services_does_not_load_alembic_or_fpdf():
    code = (
        "import sys\n"
        "import chronicler.core.services\n"
        "import chronicler.core.database_manager\n"
        "loaded = [m for m in ('alembic', 'fpdf') if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == ""
