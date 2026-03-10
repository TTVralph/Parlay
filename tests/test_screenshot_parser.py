from app.screenshot_parser import normalize_sportsbook_ocr_text, parse_screenshot_text


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


def test_bet365_player_and_market_lines_normalize_and_parse() -> None:
    raw = """
    Bet365 Bet Slip
    Nikola Jokic
    O26.5 Pts
    Russell Westbrook
    Triple Double Yes
    Cash Out
    To Pay $145.00
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert 'Nikola Jokic Over 26.5 Points' in normalized
    assert 'Russell Westbrook Triple Double Yes' in normalized
    assert 'Cash Out' not in normalized

    parsed = parse_screenshot_text(raw, raw)
    labels = [leg.normalized_label for leg in parsed.parsed_legs]
    assert 'Nikola Jokic Over 26.5 Points' in labels
    assert 'Russell Westbrook Triple Double Yes' in labels


def test_fanduel_player_plus_over_under_format_parses() -> None:
    raw = """
    FanDuel
    Jalen Brunson
    Over 25.5 Pts + Ast
    Track
    """
    parsed = parse_screenshot_text(raw, raw)
    assert len(parsed.parsed_legs) == 1
    assert parsed.parsed_legs[0].normalized_label == 'Jalen Brunson Over 25.5 Points + Assists'


def test_draftkings_shorthand_lines_parse() -> None:
    raw = """
    DraftKings
    Stephen Curry O4.5 Ast
    Anthony Davis U11.5 Reb
    Share
    Wager $20
    """
    parsed = parse_screenshot_text(raw, raw)
    labels = [leg.normalized_label for leg in parsed.parsed_legs]
    assert 'Stephen Curry Over 4.5 Assists' in labels
    assert 'Anthony Davis Under 11.5 Rebounds' in labels


def test_betmgm_double_double_yes_no_parses() -> None:
    raw = """
    BetMGM
    Bam Adebayo Double Double No
    Boost
    """
    parsed = parse_screenshot_text(raw, raw)
    assert len(parsed.parsed_legs) == 1
    assert parsed.parsed_legs[0].normalized_label == 'Bam Adebayo Double Double No'


def test_bet365_binary_prop_slip_normalization() -> None:
    raw = """
    Russell Westbrook
    Yes
    Triple-Double
    CHI Today 9:10 PM SAC
    Dejounte Murray
    Yes
    Triple-Double
    WAS Today 7:10 PM NO
    Cash Out $5.00
    Share
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == [
        'Russell Westbrook Triple Double Yes',
        'Dejounte Murray Triple Double Yes',
    ]


def test_fanduel_over_under_slip_normalization() -> None:
    raw = """
    Nikola Jokic O26.5 PTS
    Luka Doncic O8.5 AST
    Jayson Tatum U7.5 REB
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == [
        'Nikola Jokic Over 26.5 Points',
        'Luka Doncic Over 8.5 Assists',
        'Jayson Tatum Under 7.5 Rebounds',
    ]


def test_draftkings_shorthand_and_noise_filtering() -> None:
    raw = """
    DraftKings
    Stephen Curry O4.5 Ast
    +5200
    Hide Legs
    Anthony Davis U11.5 Reb
    To Pay $124
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == [
        'Stephen Curry Over 4.5 Assists',
        'Anthony Davis Under 11.5 Rebounds',
    ]


def test_betmgm_combo_prop_slip_normalization() -> None:
    raw = """
    Quentin Grimes Over 22.5 Pts + Ast
    Aaron Gordon Under 17.5 Pts + Reb
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == [
        'Quentin Grimes Over 22.5 Points + Assists',
        'Aaron Gordon Under 17.5 Points + Rebounds',
    ]


def test_common_shorthand_and_line_break_joining() -> None:
    raw = """
    Tyler Herro
    More 3.5
    3PT
    Scottie Barnes
    Less 8.5
    Reb + Ast
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == [
        'Tyler Herro Over 3.5 Threes',
        'Scottie Barnes Under 8.5 Rebounds + Assists',
    ]


def test_safe_player_typo_correction_case() -> None:
    raw = """
    Shai Gilly-Alexander Under 1.5 Threes
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized == 'Shai Gilly-Alexander Under 1.5 Threes'

    parsed = parse_screenshot_text(raw, raw)
    assert parsed.parsed_legs[0].player_name == 'Shai Gilgeous-Alexander'
    assert parsed.parsed_legs[0].suggested_player_name == 'Shai Gilgeous-Alexander'
    assert parsed.parsed_legs[0].suggestion_auto_applied is True

