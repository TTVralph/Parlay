from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_check_empty_textarea_message():
    res = client.post('/check', json={'text': '   '})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Paste at least one leg first.'
    assert body['legs'] == []


def test_check_no_legs_parsed_message(monkeypatch):
    monkeypatch.setattr('app.main.parse_text', lambda _text: [])
    res = client.post('/check', json={'text': 'LeBron over 20.5 points'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No bet legs found. Try one leg per line.'


def test_check_grading_error_message(monkeypatch):
    def _raise(_text):
        raise RuntimeError('boom')

    monkeypatch.setattr('app.main.grade_text', _raise)
    res = client.post('/check', json={'text': 'Celtics ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Could not grade this slip right now.'


def test_check_with_stake_returns_estimated_payout_and_profit():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 20})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['estimated_profit'] == 30.0
    assert body['estimated_payout'] == 50.0
    assert body['american_odds_used'] == 150


def test_check_rejects_invalid_stake():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 'abc'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Enter a valid numeric stake amount.'


def test_check_maps_pending_to_still_live():
    res = client.post('/check-slip', json={'text': 'Nikola Jokic over 250.5 passing yards'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['parlay_result'] == 'still_live'
    assert body['legs'][0]['result'] == 'pending'
