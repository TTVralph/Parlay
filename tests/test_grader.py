from datetime import datetime

from app.grader import grade_text


def test_grade_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    result = grade_text(text, posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    assert result.overall == 'lost'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'
    assert result.legs[2].settlement == 'loss'


def test_grade_unverified_slip_is_needs_review() -> None:
    result = grade_text('Leg A\nLeg B')
    assert result.overall == 'needs_review'
    assert all(item.settlement == 'unmatched' for item in result.legs)


def test_grade_live_or_unresolved_stats_is_pending() -> None:
    result = grade_text('Nikola Jokic over 250.5 passing yards')
    assert result.overall == 'needs_review'
    assert result.legs[0].settlement == 'unmatched'


def test_grade_only_verified_wins_is_cashed() -> None:
    result = grade_text('Jokic 25+ pts\nDenver ML', posted_at=datetime.fromisoformat('2026-03-07T19:00:00'))
    assert result.overall == 'cashed'
    assert all(item.settlement == 'win' for item in result.legs)
