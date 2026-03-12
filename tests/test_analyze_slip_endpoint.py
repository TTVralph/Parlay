from fastapi.testclient import TestClient

from app.main import app


def test_analyze_slip_response_shape() -> None:
    client = TestClient(app)
    res = client.post('/analyze-slip', json={'text': 'Denver ML\nJokic over 24.5 points'})
    assert res.status_code == 200
    body = res.json()
    assert body['ok'] is True
    assert body['advisory_only'] is True
    assert 'slip_risk_score' in body
    assert body['slip_risk_label'] in {'low', 'medium', 'high'}
    assert body['weakest_leg'] is not None
    assert body['safest_leg'] is not None
    assert body['likely_seller'] is not None
    assert isinstance(body['leg_risk_scores'], list)


def test_analyze_mode_does_not_change_check_slip_shape() -> None:
    client = TestClient(app)
    analyze = client.post('/analyze-slip', json={'text': 'Denver ML'})
    settle = client.post('/check-slip', json={'text': 'Denver ML'})

    assert analyze.status_code == 200
    assert settle.status_code == 200
    settle_body = settle.json()
    assert 'parlay_result' in settle_body
    assert 'legs' in settle_body
    assert 'slip_risk_score' not in settle_body


def test_unsupported_markets_visible_in_analyze_endpoint() -> None:
    client = TestClient(app)
    res = client.post('/analyze-slip', json={'text': 'LeBron first basket\nDenver ML'})
    assert res.status_code == 200
    body = res.json()
    unsupported = [leg for leg in body['leg_risk_scores'] if not leg['supported_market']]
    assert len(unsupported) == 1
    assert 'unsupported_market' in unsupported[0]['advisory_reason_codes']
