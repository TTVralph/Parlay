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
    assert body.get('public_url') == f"/parlay/{body['public_id']}"

    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'ParlayBot Result' in page.text
    assert 'Check another slip' in page.text
