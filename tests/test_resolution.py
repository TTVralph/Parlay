from datetime import datetime

from app.grader import grade_text
from app.providers.sample_provider import SampleResultsProvider



def test_date_resolution_uses_posted_time_for_denver_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts\nDenver ML',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-07T18:15:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[1].leg.event_id == 'nba-2026-03-07-den-lal'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'



def test_date_resolution_switches_to_later_jokic_game() -> None:
    provider = SampleResultsProvider()
    result = grade_text(
        'Jokic 25+ pts',
        provider=provider,
        posted_at=datetime.fromisoformat('2026-03-09T18:00:00'),
    )
    assert result.legs[0].leg.event_id == 'nba-2026-03-09-okc-den'
    assert result.legs[0].settlement == 'loss'
