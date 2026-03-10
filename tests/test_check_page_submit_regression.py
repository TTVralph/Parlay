import re

from fastapi.testclient import TestClient

from app.main import app


def test_check_page_script_keeps_submit_handler_and_prevent_default() -> None:
    client = TestClient(app)
    response = client.get('/check')
    assert response.status_code == 200
    html = response.text

    assert "form.addEventListener('submit'" in html
    assert 'event.preventDefault();' in html
    assert "fetch('/check-slip'" in html


def test_check_page_uses_escaped_newline_in_parsed_legs_join() -> None:
    client = TestClient(app)
    response = client.get('/check')
    assert response.status_code == 200

    html = response.text
    script_match = re.search(r'<script>([\s\S]*)</script>', html)
    assert script_match is not None
    script = script_match.group(1)

    assert "parsedLegs.join('\\n')" in script
    assert "parsedLegs.join('\n')" not in script


def test_check_page_script_shows_non_blocking_payout_message() -> None:
    client = TestClient(app)
    response = client.get('/check')
    assert response.status_code == 200
    html = response.text

    assert "else if(data.payout_message)" in html
    assert "payoutOut.textContent=data.payout_message;" in html
