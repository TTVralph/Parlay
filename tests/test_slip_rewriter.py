from app.models import Leg
from app.services.slip_rewriter import rewrite_slip_safer
from app.services.slip_risk_analyzer import analyze_slip_risk


def test_milestone_prop_rewrite_lowers_threshold() -> None:
    legs = [
        Leg(raw_text='Jokic over 10+ assists', sport='NBA', market_type='player_assists', player='Nikola Jokic', direction='over', line=10.0, confidence=0.9),
    ]
    analysis = analyze_slip_risk(legs)

    rewritten = rewrite_slip_safer(legs, analysis)

    assert rewritten['changed_legs_count'] == 1
    assert rewritten['rewritten_legs'][0].suggested_leg.lower().find('8') >= 0


def test_standard_line_rewrite_moves_one_safer_tier() -> None:
    legs = [
        Leg(raw_text='Shai over 28.5 points', sport='NBA', market_type='player_points', player='Shai Gilgeous-Alexander', direction='over', line=28.5, confidence=0.9),
    ]
    analysis = analyze_slip_risk(legs)

    rewritten = rewrite_slip_safer(legs, analysis)

    assert rewritten['changed_legs_count'] == 1
    assert '27.5' in rewritten['rewritten_legs'][0].suggested_leg


def test_unsupported_market_is_left_unchanged_and_flagged() -> None:
    legs = [
        Leg(raw_text='LeBron first basket +600', sport='NBA', market_type='player_first_basket', player='LeBron James', confidence=0.5),
    ]
    analysis = analyze_slip_risk(legs)

    rewritten = rewrite_slip_safer(legs, analysis)

    row = rewritten['rewritten_legs'][0]
    assert row.changed is False
    assert row.rewriteable is False
    assert row.suggested_leg == legs[0].raw_text


def test_rewritten_risk_score_is_lower_for_risky_combo_slip() -> None:
    legs = [
        Leg(raw_text='Jokic over 49.5 PRA +230', sport='NBA', market_type='player_pra', player='Nikola Jokic', direction='over', line=49.5, confidence=0.9, american_odds=230),
        Leg(raw_text='Murray over 3.5 threes +120', sport='NBA', market_type='player_threes', player='Jamal Murray', direction='over', line=3.5, confidence=0.9, american_odds=120),
    ]
    analysis = analyze_slip_risk(legs)

    rewritten = rewrite_slip_safer(legs, analysis)

    assert rewritten['rewritten_risk_score'] < analysis.slip_risk_score


def test_rewrite_is_deterministic() -> None:
    legs = [
        Leg(raw_text='Jokic over 49.5 PRA +230', sport='NBA', market_type='player_pra', player='Nikola Jokic', direction='over', line=49.5, confidence=0.9, american_odds=230),
    ]
    analysis = analyze_slip_risk(legs)

    first = rewrite_slip_safer(legs, analysis)
    second = rewrite_slip_safer(legs, analysis)

    assert first == second
