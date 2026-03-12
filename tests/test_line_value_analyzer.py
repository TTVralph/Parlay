from app.models import Leg
from app.services.line_value_analyzer import SUPPORTED_PROP_MARKETS, analyze_line_value


def test_supported_markets_include_team_and_game_lines() -> None:
    for market in ('moneyline', 'spread', 'game_total'):
        assert market in SUPPORTED_PROP_MARKETS


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
    assert analyzed.user_line == 24.5
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


def test_line_value_analyzer_scores_moneyline_using_american_odds() -> None:
    leg = Leg(
        raw_text='Denver ML -115',
        market_type='moneyline',
        team='Denver Nuggets',
        confidence=0.91,
        american_odds=-115,
        event_candidates=[
            {'provider': 'draftkings', 'american_odds': -130},
            {'provider': 'fanduel', 'odds': -125},
        ],
    )

    analyzed = analyze_line_value(leg)

    assert analyzed.market_average_line == -127.5
    assert analyzed.user_line == -115.0
    assert analyzed.line_difference == 12.5
    assert analyzed.line_value_label == 'good'


def test_line_value_analyzer_returns_unknown_when_market_data_missing() -> None:
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
    assert analyzed.user_line is None
    assert analyzed.line_difference is None
    assert analyzed.line_value_score is None
    assert analyzed.line_value_label == 'unknown'
