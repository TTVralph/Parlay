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


def test_check_slip_returns_graded_legs_with_event_and_overall():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['parlay_result'] == 'lost'
    assert [leg['result'] for leg in body['legs']] == ['win', 'win', 'loss']
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

