from fastapi.testclient import TestClient

from app.main import app


def test_check_slip_endpoint_returns_review_when_unmatched_legs():
    client = TestClient(app)

    response = client.post('/check-slip', json={'text': 'Leg A\n\n Leg B  \n'})

    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is False
    assert body['parlay_result'] == 'needs_review'
    assert body['message'] in {'No valid betting legs detected.', 'Paste at least one leg first.'}


def test_check_slip_accepts_bet_date_field():
    client = TestClient(app)
    response = client.post('/check-slip', json={'text': 'Denver ML', 'bet_date': '2026-03-09'})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert 'legs' in body


def test_check_slip_generates_public_link_and_page():
    client = TestClient(app)
    response = client.post('/check-slip', json={'text': 'Denver ML'})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body.get('public_id')
    assert body.get('public_url') == f"/r/{body['public_id']}"

    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'ParlayBot Result' in page.text
    assert 'Check another slip' in page.text


def test_check_slip_invalid_submission_does_not_persist_public_slip():
    client = TestClient(app)
    response = client.post('/check-slip', json={'text': '   '})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is False
    assert 'public_id' not in body
    assert 'public_url' not in body


def test_public_parlay_page_has_graceful_invalid_id_state():
    client = TestClient(app)
    page = client.get('/r/NOT-VALID')
    assert page.status_code == 404
    assert "couldn't open that shared slip" in page.text
    assert 'public ID format is invalid' in page.text


def test_public_parlay_page_has_graceful_not_found_state():
    client = TestClient(app)
    page = client.get('/r/aaaaaaaa')
    assert page.status_code == 404
    assert 'This public slip was not found.' in page.text
    assert 'Check a new slip' in page.text


def test_check_slip_saved_to_recent_tracker_feed():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200

    response = client.post('/check-slip', json={'text': 'Denver ML\nJokic over 24.5 points', 'bet_date': '2026-03-09', 'stake_amount': 25})
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True

    recents = client.get('/my-slips')
    assert recents.status_code == 200
    items = recents.json()['items']
    assert len(items) >= 1
    first = items[0]
    assert first['public_url'].startswith('/r/')
    assert first['summary']
    assert isinstance(first['leg_statuses'], list)
    assert first['share_url'] == first['public_url']


def test_check_page_has_my_slips_ui():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'My Slips' in html
    assert "id='recentSlipsList'" in html
    assert "fetch('/my-slips')" in html
