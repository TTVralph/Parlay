import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _extract_check_page_script() -> str:
    client = TestClient(app)
    response = client.get('/check')
    assert response.status_code == 200

    html = response.text
    script_match = re.search(r'<script>([\s\S]*)</script>', html)
    assert script_match is not None
    return script_match.group(1)


def test_check_page_script_keeps_submit_handler_and_prevent_default() -> None:
    script = _extract_check_page_script()

    assert "form.addEventListener('submit'" in script
    assert 'event.preventDefault();' in script
    assert "fetch('/check-slip'" in script


def test_check_page_uses_escaped_newline_sequences() -> None:
    script = _extract_check_page_script()

    assert "parsedLegs.join('\\n')" in script
    assert "slip.value.split('\\n')" in script
    assert "slip.value=lines.join('\\n')" in script


def test_check_page_script_is_javascript_syntax_valid() -> None:
    node = shutil.which('node')
    if node is None:
        raise AssertionError('Node.js is required for check page syntax regression test')

    script = _extract_check_page_script()
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / 'check_page_script.js'
        script_path.write_text(script)
        result = subprocess.run([node, '--check', str(script_path)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr or result.stdout


def test_check_page_script_shows_non_blocking_payout_message() -> None:
    script = _extract_check_page_script()

    assert 'else if(data.payout_message)' in script
    assert 'payoutOut.textContent=data.payout_message;' in script
