from __future__ import annotations

import shutil
import subprocess

import pytest


def test_app_main_imports_with_python312() -> None:
    py312 = shutil.which('python3.12')
    if not py312:
        pytest.skip('python3.12 is not available in this environment')

    has_fastapi = subprocess.run(
        [py312, '-c', 'import importlib.util; raise SystemExit(0 if importlib.util.find_spec("fastapi") else 1)'],
        capture_output=True,
        text=True,
    )
    if has_fastapi.returncode != 0:
        pytest.skip('python3.12 environment does not have fastapi installed')

    proc = subprocess.run(
        [py312, '-c', 'import app.main'],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
