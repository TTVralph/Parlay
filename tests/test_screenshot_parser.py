from app.screenshot_parser import parse_screenshot_text


def test_parse_screenshot_extracts_multiple_legs_and_date_and_ignores_odds() -> None:
    text = """
    Bet Slip
    Mar 6, 2026
    Draymond Green Over 4.5 Assists
    Jayson Tatum Over 31.5 Pts + Ast
    Stephen Curry Under 2.5 Threes
    Odds +520
    Stake $20
    Payout $124
    """
    parsed = parse_screenshot_text(text, text)
    assert parsed.detected_bet_date == '2026-03-06'
    assert len(parsed.parsed_legs) == 3
    labels = [leg.normalized_label.lower() for leg in parsed.parsed_legs]
    assert any('draymond green over 4.5 assists' in label for label in labels)
    assert any('jayson tatum over 31.5 points + assists' in label for label in labels)
    assert any('stephen curry under 2.5 threes' in label for label in labels)


def test_parse_screenshot_handles_noisy_line_breaks_and_dedupes() -> None:
    noisy = """
    03/06/2026
    Stephen Curry
    Under 2.5
    3PM
    Stephen Curry Under 2.5 3PM
    To Win $40
    """
    parsed = parse_screenshot_text(noisy, noisy)
    assert parsed.detected_bet_date == '2026-03-06'
    assert len(parsed.parsed_legs) == 1
    assert parsed.parsed_legs[0].direction == 'under'
    assert parsed.parsed_legs[0].stat_type == 'threes'
