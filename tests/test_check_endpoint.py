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
    assert body['parsed_legs'] == []


def test_check_no_legs_parsed_message(monkeypatch):
    monkeypatch.setattr('app.main.parse_text', lambda _text: [])
    res = client.post('/check', json={'text': 'LeBron over 20.5 points'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No valid betting legs detected.'
    assert body['parse_warning'] == 'No valid betting legs detected.'


def test_check_grading_error_message(monkeypatch):
    def _raise(_text):
        raise RuntimeError('boom')

    monkeypatch.setattr('app.main.grade_text', _raise)
    res = client.post('/check', json={'text': 'Celtics ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Could not grade this slip right now.'
    assert body['grading_warning'] == 'Parsed legs were detected, but grading did not complete.'


def test_check_with_stake_returns_estimated_payout_and_profit():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 20})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['estimated_profit'] == 30.0
    assert body['estimated_payout'] == 50.0
    assert body['american_odds_used'] == 150
    assert body['parsed_legs'] == ['Denver ML']


def test_check_rejects_invalid_stake():
    res = client.post('/check-slip', json={'text': 'Denver ML\nOdds +150', 'stake_amount': 'abc'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Enter a valid numeric stake amount.'
    assert body['parsed_legs'] == []


def test_check_maps_pending_to_still_live():
    res = client.post('/check-slip', json={'text': 'Nikola Jokic over 250.5 passing yards'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['parlay_result'] in {'still_live', 'needs_review'}
    assert body['legs'][0]['result'] in {'pending', 'review'}


def test_check_sets_grading_warning_when_all_legs_unmatched(monkeypatch):
    from app.models import GradeResponse, GradedLeg, Leg

    def _grade(_text, provider=None, posted_at=None):
        leg = Leg(raw_text='Denver ML', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95)
        return GradeResponse(overall='needs_review', legs=[GradedLeg(leg=leg, settlement='unmatched', reason='x')])

    monkeypatch.setattr('app.main.grade_text', _grade)
    res = client.post('/check-slip', json={'text': 'Denver ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['grading_warning'] == 'Parsed legs were detected, but ESPN matching could not settle any leg.'


def test_check_nonsense_input_is_rejected():
    res = client.post('/check-slip', json={'text': 'hello\nthis is a test\nrandom bet'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No valid betting legs detected.'
    assert body['legs'] == []
