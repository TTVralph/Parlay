from fastapi.testclient import TestClient

from app.main import app
from app.grader import _compute_parlay_closeness
from app.models import GradedLeg, Leg


def _leg(name: str, line: float, actual: float, settlement: str) -> GradedLeg:
    return GradedLeg(
        leg=Leg(raw_text=f"{name} over {line} points", market_type='player_points', player=name, line=line),
        settlement=settlement,
        actual_value=actual,
        reason='test',
        line=line,
        normalized_market='player_points',
        matched_event='Rockets @ Nuggets',
    )


def test_parlay_closeness_score_calculation():
    score, closest, worst = _compute_parlay_closeness([
        _leg('Kevin Durant', 20, 11, 'loss'),
        _leg('Jakob Poeltl', 8, 5, 'loss'),
        _leg('Paolo Banchero', 18, 22, 'win'),
    ])
    assert score is not None
    assert 0 <= score <= 100
    assert closest is not None and closest['player_or_team'] == 'Jakob Poeltl'
    assert worst is not None and worst['player_or_team'] == 'Kevin Durant'


def test_check_slip_exposes_closeness_and_short_public_route():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Denver ML'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['public_url'].startswith('/r/')
    assert 'parlay_closeness_score' in body
    assert 'closest_miss_leg' in body
    assert 'worst_miss_leg' in body


def test_short_public_route_renders_page():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Denver ML'})
    body = resp.json()
    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'ParlayBot Result' in page.text
