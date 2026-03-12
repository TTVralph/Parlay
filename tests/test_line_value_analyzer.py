from app.models import Leg
from app.services.line_value_analyzer import analyze_line_value


def test_line_value_analyzer_scores_good_line_for_over_when_user_line_below_market() -> None:
    leg = Leg(
        raw_text='Jokic over 24.5 points',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.9,
        event_candidates=[
            {'provider': 'draftkings', 'line': 25.5},
            {'provider': 'fanduel', 'market_line': 25.0},
        ],
    )

    analyzed = analyze_line_value(leg)

    assert analyzed.market_average_line == 25.25
    assert analyzed.line_difference == -0.75
    assert analyzed.line_value_score is not None and analyzed.line_value_score > 0
    assert analyzed.line_value_label == 'good'


def test_line_value_analyzer_scores_bad_line_for_under_when_user_line_below_market() -> None:
    leg = Leg(
        raw_text='Jokic under 24.5 points',
        market_type='player_points',
        player='Nikola Jokic',
        direction='under',
        line=24.5,
        confidence=0.9,
        event_candidates=[
            {'provider': 'draftkings', 'line': 25.5},
            {'provider': 'fanduel', 'market_line': 25.0},
        ],
    )

    analyzed = analyze_line_value(leg)

    assert analyzed.line_value_score is not None and analyzed.line_value_score < 0
    assert analyzed.line_value_label == 'bad'


def test_line_value_analyzer_returns_neutral_when_market_data_missing() -> None:
    leg = Leg(
        raw_text='Jokic over 24.5 points',
        market_type='player_points',
        player='Nikola Jokic',
        direction='over',
        line=24.5,
        confidence=0.9,
    )

    analyzed = analyze_line_value(leg)

    assert analyzed.market_average_line is None
    assert analyzed.line_difference is None
    assert analyzed.line_value_score is None
    assert analyzed.line_value_label == 'neutral'
