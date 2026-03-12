from app.models import Leg
from app.services.slip_risk_analyzer import analyze_leg_risk, analyze_slip_risk, detect_trap_leg


def test_deterministic_leg_ranking_and_extremes() -> None:
    low = Leg(raw_text='Denver ML -180', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, american_odds=-180)
    high = Leg(raw_text='Jokic over 39.5 points +210', sport='NBA', market_type='player_points', player='Nikola Jokic', direction='over', line=39.5, confidence=0.92, american_odds=210)
    mid = Leg(raw_text='Murray over 2.5 threes +100', sport='NBA', market_type='player_threes', player='Jamal Murray', direction='over', line=2.5, confidence=0.9, american_odds=100)

    result = analyze_slip_risk([low, high, mid])

    assert result.ok is True
    assert result.weakest_leg is not None and result.weakest_leg.raw_leg_text == high.raw_text
    assert result.safest_leg is not None and result.safest_leg.raw_leg_text == low.raw_text
    assert result.likely_seller is not None and result.likely_seller.raw_leg_text == high.raw_text
    assert result.trap_leg is not None and result.trap_leg.raw_leg_text == high.raw_text
    assert result.trap_score > 0
    assert isinstance(result.trap_reason_codes, list)
    assert [leg.raw_leg_text for leg in sorted(result.leg_risk_scores, key=lambda item: item.risk_score)] == [low.raw_text, mid.raw_text, high.raw_text]


def test_unsupported_markets_remain_visible_with_warnings() -> None:
    unsupported = Leg(raw_text='LeBron first basket +600', sport='NBA', market_type='player_first_basket', player='LeBron James', confidence=0.4, american_odds=600)
    supported = Leg(raw_text='Denver ML -120', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, american_odds=-120)

    result = analyze_slip_risk([unsupported, supported])

    assert len(result.leg_risk_scores) == 2
    first = next(item for item in result.leg_risk_scores if item.raw_leg_text == unsupported.raw_text)
    assert first.supported_market is False
    assert 'unsupported_market' in first.advisory_reason_codes
    assert 'limited_confidence' in first.advisory_reason_codes
    assert result.unsupported_leg_count == 1


def test_analyze_leg_shape_contains_required_fields() -> None:
    leg = Leg(raw_text='Shai over 5.5 assists -105', sport='NBA', market_type='player_assists', player='Shai Gilgeous-Alexander', direction='over', line=5.5, confidence=0.91, american_odds=-105)
    analyzed = analyze_leg_risk(leg)

    assert analyzed.market_type == 'player_assists'
    assert analyzed.subject_name
    assert isinstance(analyzed.risk_score, float)
    assert analyzed.risk_label in {'low', 'medium', 'high'}
    assert analyzed.explanation
    assert isinstance(analyzed.advisory_reason_codes, list)



def test_trap_leg_selection_prefers_inflated_combo_longshot() -> None:
    safe = Leg(raw_text='Denver ML -180', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, american_odds=-180)
    trap = Leg(raw_text='Jokic over 49.5+ PRA +230', sport='NBA', market_type='player_pra', player='Nikola Jokic', direction='over', line=49.5, confidence=0.9, american_odds=230)
    mid = Leg(raw_text='Murray over 22.5 points +100', sport='NBA', market_type='player_points', player='Jamal Murray', direction='over', line=22.5, confidence=0.9, american_odds=100)

    trap_leg, trap_score, codes = detect_trap_leg([safe, trap, mid])

    assert trap_leg is not None
    assert trap_leg.raw_leg_text == trap.raw_text
    assert trap_score > 0
    assert 'trap_line_distance_penalty' in codes
    assert 'trap_combo_market_inflation_penalty' in codes
    assert 'trap_alt_line_penalty' in codes
    assert 'trap_longshot_odds_penalty' in codes


def test_trap_leg_scoring_is_deterministic() -> None:
    legs = [
        Leg(raw_text='Denver ML -120', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, american_odds=-120),
        Leg(raw_text='Jokic over 43.5 points +190', sport='NBA', market_type='player_points', player='Nikola Jokic', direction='over', line=43.5, confidence=0.9, american_odds=190),
    ]

    first = detect_trap_leg(legs)
    second = detect_trap_leg(legs)
    assert first == second


def test_trap_leg_handles_unsupported_market_gracefully() -> None:
    unsupported = Leg(raw_text='LeBron first basket +600', sport='NBA', market_type='player_first_basket', player='LeBron James', confidence=0.4, american_odds=600)
    supported = Leg(raw_text='Denver ML -120', sport='NBA', market_type='moneyline', team='Denver Nuggets', confidence=0.95, american_odds=-120)

    trap_leg, trap_score, codes = detect_trap_leg([unsupported, supported])

    assert trap_leg is not None
    assert trap_score >= 0
    assert isinstance(codes, list)
