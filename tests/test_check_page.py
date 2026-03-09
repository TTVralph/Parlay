from fastapi.testclient import TestClient

from app.main import app


def test_check_page_has_loading_state_and_friendly_layout():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Did This Parlay Cash?' in html
    assert 'Check Slip' in html
    assert 'Checking your slip...' in html
    assert 'btn.disabled=true' in html
    assert 'Paste at least one leg first, or upload a screenshot.' in html
    assert 'Paste at least one leg first.' in html
    assert '<th>Leg</th>' in html
    assert '<th>Result</th>' in html
    assert '<th>Matched event</th>' in html
    assert "id='debugOut'" in html
    assert 'OCR extracted text:' in html
    assert 'Parsed legs before grading:' in html
    assert 'No valid bet legs were detected from this input.' in html


def test_check_slip_returns_graded_legs_with_event_and_overall():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['parlay_result'] in {'lost', 'needs_review', 'still_live', 'cashed'}
    assert len(body['legs']) == 3
    assert all('matched_event' in leg for leg in body['legs'])





def test_check_page_has_copy_summary_controls_and_format():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Copy Summary' in html
    assert 'buildSummary' in html
    assert 'Parlay:' in html
    assert "resultEmoji={win:'✅',loss:'❌'" in html


def test_check_page_supports_screenshot_upload_flow():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='slipImage'" in html
    assert "accept='image/*'" in html
    assert "fetch('/ingest/screenshot/grade'" in html
    assert 'normalizeScreenshotPayload' in html
    assert 'grading_warning' in html
    assert 'parse_warning' in html


def test_check_page_shows_optional_stake_input():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='stakeAmount'" in html
    assert 'Stake amount (optional)' in html


def test_check_page_only_renders_manual_override_controls_when_candidates_exist():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'if(candidateGames.length>0)' in html
    assert 'candidateGamesByLegId' not in html


def test_check_page_shows_bet_date_input():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Bet Date' in html
    assert "id='slipDate'" in html
    assert 'Optional, but strongly recommended' in html
