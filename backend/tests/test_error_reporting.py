"""What error reports may carry. A creator's key must never be in one."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]

# Run in its own process, with a stand-in for the library, so that importing
# the app with reporting switched on touches nothing else in the test run.
_IMPORT_APP = """
import json, sys, types
fake = types.ModuleType("sentry_sdk")
fake.init = lambda **options: print(json.dumps(options))
sys.modules["sentry_sdk"] = fake
import main
"""


def test_error_reports_carry_no_local_variables():
    done = subprocess.run(
        [sys.executable, "-c", _IMPORT_APP],
        cwd=_BACKEND,
        env={**os.environ, "SENTRY_DSN": "https://public@example.invalid/1"},
        capture_output=True,
        text=True,
        check=True,
    )
    options = json.loads(done.stdout.strip().splitlines()[-1])
    # A frame's locals include the request scope, headers and all.
    assert options["include_local_variables"] is False
    assert options["send_default_pii"] is False


def test_the_option_is_one_the_installed_library_knows():
    # A misspelt option would be accepted by the stand-in above.
    consts = pytest.importorskip("sentry_sdk.consts")
    assert "include_local_variables" in consts.DEFAULT_OPTIONS
