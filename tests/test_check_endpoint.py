from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_check_empty_textarea_message():
    res = client.post('/check', json={'text': '   '})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'Paste your bet slip first so we can check it.'
    assert body['legs'] == []


def test_check_no_legs_parsed_message(monkeypatch):
    monkeypatch.setattr('app.main.parse_text', lambda _text: [])
    res = client.post('/check', json={'text': 'LeBron over 20.5 points'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'No legs detected. Try pasting one leg per line.'


def test_check_unsupported_market_message():
    res = client.post('/check', json={'text': 'totally unsupported market syntax'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert 'do not support yet' in body['message']
    assert body['unsupported_legs'] == ['totally unsupported market syntax']


def test_check_grading_error_message(monkeypatch):
    def _raise(_text):
        raise RuntimeError('boom')

    monkeypatch.setattr('app.main.grade_text', _raise)
    res = client.post('/check', json={'text': 'Celtics ML'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is False
    assert body['message'] == 'We hit a grading error while checking your slip. Please try again in a minute.'
