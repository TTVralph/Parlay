from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_app_main_compiles_with_python312() -> None:
    py312 = shutil.which('python3.12')
    if not py312:
        pytest.skip('python3.12 is not available in this environment')

    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / 'app' / 'main.py'
    proc = subprocess.run([py312, '-m', 'py_compile', str(target)], capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr or proc.stdout
