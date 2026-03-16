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
    assert body['trap_leg'] is not None
    assert isinstance(body['trap_score'], float)
    assert isinstance(body['trap_reason_codes'], list)
    assert isinstance(body['leg_risk_scores'], list)
    assert 'same_game_group_count' in body
    assert 'same_game_leg_count' in body
    assert body['correlation_risk_label'] in {'low', 'medium', 'high'}
    assert 'estimated_hit_rate' in body
    assert 'fair_odds' in body
    first_leg = body['leg_risk_scores'][0]
    assert 'market_average_line' in first_leg
    assert 'user_line' in first_leg
    assert 'line_difference' in first_leg
    assert 'line_value_score' in first_leg
    assert first_leg['line_value_label'] in {'good', 'neutral', 'bad', 'unknown'}
    assert 'line_value_source' in first_leg
    assert 'line_edge' in first_leg
    assert 'consensus_available' in first_leg
    assert 'rewritten_slip_text' in body
    assert isinstance(body['rewritten_legs'], list)
    assert 'rewritten_risk_score' in body
    assert body['rewritten_risk_label'] in {'low', 'medium', 'high'}
    assert 'changed_legs_count' in body
    assert isinstance(body['rewrite_notes'], list)
    assert 'original_vs_rewritten_summary' in body
    assert 'original_estimated_odds' in body
    assert 'rewritten_estimated_odds' in body
    assert 'risk_reduction_percent' in body


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


def test_analyze_supported_prop_handles_missing_market_data_gracefully() -> None:
    client = TestClient(app)
    res = client.post('/analyze-slip', json={'text': 'Jokic over 24.5 points'})
    assert res.status_code == 200
    body = res.json()
    leg = body['leg_risk_scores'][0]
    assert leg['market_type'] == 'player_points'
    assert leg['market_average_line'] is None
    assert leg['line_difference'] is None
    assert leg['line_value_score'] is None
    assert leg['line_value_label'] == 'unknown'
    assert leg['line_value_text'] == 'Consensus line unavailable. Using statistical baseline.'
    assert leg['line_value_source'] == 'statistical_baseline'
    assert 'risk read' in leg['short_advisory_text']


def test_endpoint_correlation_note_for_same_game_legs() -> None:
    client = TestClient(app)
    res = client.post('/analyze-slip', json={'text': 'DEN vs LAL\nJokic over 26.5 points\nMurray over 2.5 threes\nDenver ML'})
    assert res.status_code == 200
    body = res.json()
    assert 'correlation_note' in body
    assert isinstance(body['correlation_note'], str)


def test_milestone_props_expose_normalized_line() -> None:
    client = TestClient(app)
    res = client.post('/analyze-slip', json={'text': 'Jokic to score 10+ points'})
    assert res.status_code == 200
    body = res.json()
    leg = body['leg_risk_scores'][0]
    assert leg['original_leg_text'] == 'Jokic to score 10+ points'
    assert leg['normalized_line_value'] == 9.5
