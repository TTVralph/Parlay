from app.main import _slip_status_summary
from app.parser import parse_text
from app.screenshot_parser import normalize_sportsbook_ocr_text, parse_screenshot_text


def test_three_pointer_market_variants_parse_and_stay_visible() -> None:
    raw = """
    Reed Sheppard Over 2.5 Three Pointers Made
    RJ Barrett Over 1.5 Three-Pointers Made
    Kevin Durant Over 3.5 3PM
    """
    parsed = parse_screenshot_text(raw, raw)
    labels = [leg.normalized_label for leg in parsed.parsed_legs]
    assert any('Three Pointers Made' in label or 'Threes' in label for label in labels)
    assert len(labels) == 3


def test_threshold_first_slash_format_normalizes() -> None:
    raw = """
    20+ / Kevin Durant Points
    10+ / Nikola Jokic Rebounds
    3+ / Reed Sheppard Three Pointers Made
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert 'Kevin Durant Over 19.5 Points' in normalized
    assert 'Nikola Jokic Over 9.5 Rebounds' in normalized
    assert 'Reed Sheppard Over 2.5 Threes' in normalized


def test_grouped_sgp_and_split_fragments_parse_all_legs() -> None:
    raw = """
    Same Game Parlay
    Amen Thompson
    TO RECORD
    4+ ASSISTS
    Trae Young
    POINTS + ASSISTS
    18+
    Paolo Banchero
    REBOUNDS
    6+
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert 'Amen Thompson Over 3.5 Assists' in normalized
    assert 'Trae Young Over 17.5 Points + Assists' in normalized
    assert 'Paolo Banchero Over 5.5 Rebounds' in normalized


def test_noise_headers_are_filtered() -> None:
    raw = """
    Fanatics Sportsbook
    Bet Placed
    7 Pick Parlay
    +842
    Total Wager
    Kevin Durant Over 24.5 Points
    Cash Out
    """
    normalized = normalize_sportsbook_ocr_text(raw)
    assert normalized.splitlines() == ['Kevin Durant Over 24.5 Points']


def test_time_window_market_is_review_safe_not_winloss_path() -> None:
    legs = parse_text('Kevin Durant 10+ Points in the first half')
    assert len(legs) == 1
    assert any('Unsupported time-window market' in note for note in legs[0].notes)
    assert legs[0].confidence < 0.75


def test_status_summary_excludes_review_and_void_from_hit_math() -> None:
    unresolved = _slip_status_summary([
        {'result': 'win'}, {'result': 'win'}, {'result': 'win'}, {'result': 'win'}, {'result': 'win'}, {'result': 'review'}, {'result': 'review'}
    ])
    assert '5 legs resolved' in unresolved or '5 wins' in unresolved

    with_void = _slip_status_summary([
        {'result': 'win'}, {'result': 'win'}, {'result': 'win'}, {'result': 'loss'}, {'result': 'loss'}, {'result': 'loss'}, {'result': 'void'}
    ])
    assert 'graded legs' in with_void


def test_parser_is_deterministic_for_grouped_input() -> None:
    raw = """
    same game parlay
    suns @ rockets
    kevin durant
    points
    over 24.5
    alperen sengun
    rebounds + assists
    under 15.5
    """
    outputs = [normalize_sportsbook_ocr_text(raw) for _ in range(5)]
    assert all(out == outputs[0] for out in outputs)
