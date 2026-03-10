from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import PublicSlipResultORM
from app.db.session import SessionLocal
from app.main import app


BASE_RESPONSE_KEYS = {
    'ok',
    'message',
    'legs',
    'parsed_legs',
    'parse_warning',
    'grading_warning',
    'parlay_result',
    'parse_confidence',
}


def _post_check_slip(client: TestClient, payload: dict) -> dict:
    response = client.post('/check-slip', json=payload)
    assert response.status_code == 200
    body = response.json()
    assert BASE_RESPONSE_KEYS.issubset(body.keys())
    return body


def test_check_slip_regression_matrix_covers_common_payload_shapes(monkeypatch) -> None:
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    client = TestClient(app)

    long_slip = '\n'.join(['Denver ML' for _ in range(25)])

    cases = [
        {'name': 'clean_nba_slip', 'payload': {'text': 'Jokic over 24.5 points\nDenver ML'}, 'expect_ok': True},
        {'name': 'long_slip', 'payload': {'text': long_slip}, 'expect_ok': True},
        {
            'name': 'per_leg_odds',
            'payload': {'text': 'Draymond Green Over 5.5 Assists +500\nQuentin Grimes Over 22.5 Pts + Ast +250', 'stake_amount': 100},
            'expect_ok': True,
        },
        {'name': 'stake_without_odds', 'payload': {'text': 'Denver ML', 'stake_amount': 20}, 'expect_ok': True},
        {'name': 'stake_with_odds', 'payload': {'text': 'Denver ML\nOdds +150', 'stake_amount': 20}, 'expect_ok': True},
        {'name': 'nonsense_input', 'payload': {'text': 'hello world\nthis is not a slip\nfoobar baz'}, 'expect_ok': False},
    ]

    for case in cases:
        body = _post_check_slip(client, case['payload'])
        assert body['ok'] is case['expect_ok'], case['name']

        if case['name'] == 'per_leg_odds':
            assert body['estimated_payout'] == 2100.0
            assert body['american_odds_used'] == [500, 250]
        elif case['name'] == 'stake_without_odds':
            assert body['payout_message'] == 'Add odds in your slip text (for example +120) to estimate payout.'
            assert 'estimated_payout' not in body
        elif case['name'] == 'stake_with_odds':
            assert body['estimated_payout'] == 50.0
            assert body['estimated_profit'] == 30.0
        elif case['name'] == 'nonsense_input':
            assert body['message'] == 'No valid betting legs detected.'
            assert body['legs'] == []


def test_check_slip_repeated_same_submission_keeps_shape_and_persists_unique_public_ids(monkeypatch) -> None:
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    client = TestClient(app)

    payload = {'text': 'Denver ML\nJokic over 24.5 points'}
    responses = [_post_check_slip(client, payload) for _ in range(8)]

    first = responses[0]
    for body in responses[1:]:
        for key in BASE_RESPONSE_KEYS:
            assert key in body
            assert type(body[key]) is type(first[key])

    public_ids = [item['public_id'] for item in responses if item.get('public_id')]
    assert len(public_ids) == len(responses)
    assert len(set(public_ids)) == len(public_ids)

    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(PublicSlipResultORM))
        persisted = db.scalars(
            select(PublicSlipResultORM).where(PublicSlipResultORM.raw_slip_text == payload['text'].strip())
        ).all()

    assert len(persisted) >= len(responses)
    assert total >= len(responses)


def test_check_slip_response_shape_consistency_between_stake_modes(monkeypatch) -> None:
    monkeypatch.setattr('app.main._enforce_public_check_rate_limit', lambda request, response, key: None)
    client = TestClient(app)

    base = _post_check_slip(client, {'text': 'Denver ML'})
    with_stake = _post_check_slip(client, {'text': 'Denver ML', 'stake_amount': 100})
    with_stake_and_odds = _post_check_slip(client, {'text': 'Denver ML\nOdds +150', 'stake_amount': 100})

    for key in BASE_RESPONSE_KEYS:
        assert key in base
        assert key in with_stake
        assert key in with_stake_and_odds

    assert with_stake['payout_message']
    assert with_stake_and_odds['estimated_payout'] == 250.0
