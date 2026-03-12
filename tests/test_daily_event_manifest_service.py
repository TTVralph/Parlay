from __future__ import annotations

from datetime import date, datetime

from app.models import Leg
from app.providers.base import EventInfo
from app.resolver import resolve_leg_events
from app.services.daily_event_manifest import DailyEventManifestService


class _StubScoreboardProvider:
    def __init__(self) -> None:
        self.fetch_raw_calls: list[str] = []
        self.resolve_calls: list[tuple[str, str | None, str | None]] = []

    def fetch_raw(self, date_str: str):
        self.fetch_raw_calls.append(date_str)
        return {
            'events': [
                {
                    'id': 'espn-den-bos',
                    'date': '2026-03-06T02:00:00Z',
                    'shortName': 'BOS @ DEN',
                    'competitions': [
                        {
                            'date': '2026-03-06T02:00:00Z',
                            'status': {'type': {'state': 'pre', 'completed': False}},
                            'competitors': [
                                {
                                    'homeAway': 'home',
                                    'team': {'displayName': 'Denver Nuggets', 'abbreviation': 'DEN', 'shortDisplayName': 'Nuggets'},
                                },
                                {
                                    'homeAway': 'away',
                                    'team': {'displayName': 'Boston Celtics', 'abbreviation': 'BOS', 'shortDisplayName': 'Celtics'},
                                },
                            ],
                        }
                    ],
                }
            ]
        }

    def normalize_event(self, raw_event):
        return {
            'event_id': raw_event['id'],
            'date': raw_event['date'],
            'short_name': raw_event['shortName'],
            'home_team': 'Denver Nuggets',
            'away_team': 'Boston Celtics',
            'home_team_abbr': 'DEN',
            'away_team_abbr': 'BOS',
            'competitors': [
                {'name': 'Denver Nuggets', 'abbr': 'DEN', 'short_name': 'Nuggets'},
                {'name': 'Boston Celtics', 'abbr': 'BOS', 'short_name': 'Celtics'},
            ],
            'status': 'pre',
        }

    def resolve_event_candidates(self, date_str: str, *, team_query: str | None = None, opponent_query: str | None = None):
        self.resolve_calls.append((date_str, team_query, opponent_query))
        return [
            {
                'event_id': 'espn-den-bos',
                'date': '2026-03-06T02:00:00Z',
                'short_name': 'BOS @ DEN',
                'home_team': 'Denver Nuggets',
                'away_team': 'Boston Celtics',
                'home_team_abbr': 'DEN',
                'away_team_abbr': 'BOS',
            }
        ]


class _AmbiguousDateProvider:
    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return None

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
        return [
            EventInfo(
                event_id='evt-den-bos',
                sport='NBA',
                home_team='Denver Nuggets',
                away_team='Boston Celtics',
                start_time=datetime.fromisoformat('2026-03-06T02:00:00+00:00'),
            ),
            EventInfo(
                event_id='evt-den-uta',
                sport='NBA',
                home_team='Denver Nuggets',
                away_team='Utah Jazz',
                start_time=datetime.fromisoformat('2026-03-06T04:00:00+00:00'),
            ),
        ]

    def did_player_appear(self, player: str, event_id: str):
        return None


def test_daily_manifest_builds_once_per_date() -> None:
    scoreboard = _StubScoreboardProvider()
    service = DailyEventManifestService(scoreboard_provider=scoreboard)

    first = service.get_daily_manifest('NBA', '2026-03-06')
    second = service.get_daily_manifest('NBA', date(2026, 3, 6))

    assert first is second
    assert scoreboard.fetch_raw_calls == ['2026-03-06']


def test_resolver_reuses_manifest_across_multiple_legs() -> None:
    scoreboard = _StubScoreboardProvider()
    manifest_service = DailyEventManifestService(scoreboard_provider=scoreboard)
    legs = [
        Leg(raw_text='Jamal Murray over 20.5 points', sport='NBA', market_type='player_points', player='Jamal Murray', direction='over', line=20.5, confidence=0.9),
        Leg(raw_text='Nikola Jokic over 10.5 rebounds', sport='NBA', market_type='player_rebounds', player='Nikola Jokic', direction='over', line=10.5, confidence=0.9),
    ]

    resolved = resolve_leg_events(
        legs,
        _AmbiguousDateProvider(),
        posted_at=date(2026, 3, 6),
        include_historical=True,
        scoreboard_provider=scoreboard,
        daily_manifest_service=manifest_service,
    )

    assert [item.event_id for item in resolved] == ['evt-den-bos', 'evt-den-bos']
    assert scoreboard.fetch_raw_calls == ['2026-03-06']
    assert scoreboard.resolve_calls == []


def test_resolver_falls_back_when_manifest_unavailable() -> None:
    scoreboard = _StubScoreboardProvider()

    class _FailingManifestService:
        def get_daily_manifest(self, sport: str, date_value):
            raise RuntimeError('manifest unavailable')

        def find_candidate_events_for_leg(self, manifest, leg: Leg):
            return []

    leg = Leg(raw_text='Jamal Murray over 20.5 points', sport='NBA', market_type='player_points', player='Jamal Murray', direction='over', line=20.5, confidence=0.9)

    resolved = resolve_leg_events(
        [leg],
        _AmbiguousDateProvider(),
        posted_at=date(2026, 3, 6),
        include_historical=True,
        scoreboard_provider=scoreboard,
        daily_manifest_service=_FailingManifestService(),
    )

    assert resolved[0].event_id == 'evt-den-bos'
    assert scoreboard.resolve_calls == [('2026-03-06', 'Denver Nuggets', None)]
