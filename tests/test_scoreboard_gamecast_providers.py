from __future__ import annotations

from datetime import datetime, timezone

from app.providers.base import EventInfo
from app.services.gamecast_provider import ESPNGamecastProvider
from app.services.nba_game_resolver import resolve_player_game
from app.services.provider_router import ProviderRouter
from app.services.scoreboard_provider import ESPNScoreboardProvider


class _BoxScoreProvider:
    pass


class _PlayByPlayProvider:
    pass


def test_scoreboard_provider_normalizes_events() -> None:
    provider = ESPNScoreboardProvider()
    provider._cache['20260306'] = {
        'events': [
            {
                'id': '401700001',
                'shortName': 'BOS @ DEN',
                'competitions': [
                    {
                        'date': '2026-03-06T00:30:00Z',
                        'status': {'type': {'state': 'post', 'completed': True}},
                        'competitors': [
                            {'homeAway': 'home', 'team': {'displayName': 'Denver Nuggets', 'abbreviation': 'DEN'}},
                            {'homeAway': 'away', 'team': {'displayName': 'Boston Celtics', 'abbreviation': 'BOS'}},
                        ],
                    }
                ],
            }
        ]
    }

    events = provider.fetch_events_for_date('2026-03-06')

    assert len(events) == 1
    assert events[0]['event_id'] == '401700001'
    assert events[0]['home_team'] == 'Denver Nuggets'
    assert events[0]['away_team_abbr'] == 'BOS'
    assert events[0]['is_final'] is True


def test_scoreboard_provider_resolves_team_candidates() -> None:
    provider = ESPNScoreboardProvider()
    provider._cache['20260306'] = {
        'events': [
            {
                'id': 'evt-1',
                'shortName': 'BOS @ DEN',
                'competitions': [
                    {
                        'date': '2026-03-06T00:30:00Z',
                        'status': {'type': {'state': 'pre', 'completed': False}},
                        'competitors': [
                            {'homeAway': 'home', 'team': {'displayName': 'Denver Nuggets', 'abbreviation': 'DEN'}},
                            {'homeAway': 'away', 'team': {'displayName': 'Boston Celtics', 'abbreviation': 'BOS'}},
                        ],
                    }
                ],
            },
            {
                'id': 'evt-2',
                'shortName': 'NYK @ MIA',
                'competitions': [
                    {
                        'date': '2026-03-06T01:30:00Z',
                        'status': {'type': {'state': 'pre', 'completed': False}},
                        'competitors': [
                            {'homeAway': 'home', 'team': {'displayName': 'Miami Heat', 'abbreviation': 'MIA'}},
                            {'homeAway': 'away', 'team': {'displayName': 'New York Knicks', 'abbreviation': 'NYK'}},
                        ],
                    }
                ],
            },
        ]
    }

    candidates = provider.resolve_event_candidates('2026-03-06', team_query='DEN', opponent_query='BOS')
    assert [item['event_id'] for item in candidates] == ['evt-1']


def test_gamecast_provider_normalizes_live_context() -> None:
    provider = ESPNGamecastProvider()
    provider._cache['evt-1'] = {
        'id': 'evt-1',
        'header': {
            'competitions': [
                {
                    'status': {
                        'type': {
                            'state': 'in',
                            'description': 'In Progress',
                            'detail': 'Q2 04:22',
                            'completed': False,
                        },
                        'period': 2,
                        'displayClock': '4:22',
                    }
                }
            ]
        },
        'quarter': 2,
        'clock': '4:22',
        'situation': {'possession': {'displayName': 'Denver Nuggets'}, 'lastPlay': {'text': 'Jokic makes two point shot'}},
        'leaders': [{'name': 'points'}],
        'odds': [{'provider': {'name': 'ESPN BET'}}],
    }

    normalized = provider.fetch_normalized('evt-1')

    assert normalized is not None
    assert normalized['event_id'] == 'evt-1'
    assert normalized['status']['state'] == 'in'
    assert normalized['period'] == 2
    assert normalized['situation']['possession'] == 'Denver Nuggets'


def test_provider_router_preserves_existing_routes_with_new_support_providers() -> None:
    router = ProviderRouter(
        box_score_provider=_BoxScoreProvider(),
        play_by_play_provider=_PlayByPlayProvider(),
        scoreboard_provider=ESPNScoreboardProvider(),
        gamecast_provider=ESPNGamecastProvider(),
    )

    assert router.route('player_points').data_source == 'box_score'
    assert router.route('player_first_basket').data_source == 'play_by_play'
    assert isinstance(router.scoreboard_provider, ESPNScoreboardProvider)
    assert isinstance(router.gamecast_provider, ESPNGamecastProvider)


def test_resolve_player_game_uses_scoreboard_when_provider_candidates_are_ambiguous() -> None:
    class _AmbiguousProvider:
        def resolve_team_event_candidates(self, team, as_of, *, include_historical=False):
            return [
                EventInfo(event_id='a', sport='NBA', home_team='Boston Celtics', away_team='Denver Nuggets', start_time=datetime(2026, 3, 6, tzinfo=timezone.utc)),
                EventInfo(event_id='b', sport='NBA', home_team='Denver Nuggets', away_team='Boston Celtics', start_time=datetime(2026, 3, 6, 1, tzinfo=timezone.utc)),
            ]

    scoreboard = ESPNScoreboardProvider()
    scoreboard._cache['20260306'] = {
        'events': [
            {
                'id': 'evt-unique',
                'shortName': 'BOS @ DEN',
                'competitions': [
                    {
                        'date': '2026-03-06T00:30:00Z',
                        'status': {'type': {'state': 'pre', 'completed': False}},
                        'competitors': [
                            {'homeAway': 'home', 'team': {'displayName': 'Denver Nuggets', 'abbreviation': 'DEN'}},
                            {'homeAway': 'away', 'team': {'displayName': 'Boston Celtics', 'abbreviation': 'BOS'}},
                        ],
                    }
                ],
            }
        ]
    }

    game = resolve_player_game('Jaylen Brown', '2026-03-06', provider=_AmbiguousProvider(), scoreboard_provider=scoreboard)
    assert game is not None
    assert game.event_id == 'evt-unique'


def test_providers_fail_gracefully_on_missing_payloads() -> None:
    scoreboard = ESPNScoreboardProvider()
    gamecast = ESPNGamecastProvider()

    assert scoreboard.fetch_events_for_date('2026-03-06') == []
    assert gamecast.fetch_normalized('missing-event') is None



def test_scoreboard_provider_caches_by_date(monkeypatch) -> None:
    provider = ESPNScoreboardProvider()
    calls: list[str] = []

    def _mock_fetch(url: str, params: dict[str, str] | None = None):
        calls.append(str((params or {}).get('dates')))
        return {'events': []}

    monkeypatch.setattr(provider, '_fetch_json', _mock_fetch)

    provider.fetch_raw('2026-03-06')
    provider.fetch_raw('2026-03-06')
    provider.fetch_raw('2026-03-07')

    assert calls == ['20260306', '20260307']


def test_gamecast_provider_cache_hit_and_miss(monkeypatch) -> None:
    provider = ESPNGamecastProvider()
    calls: list[str] = []

    def _mock_fetch(url: str, params: dict[str, str] | None = None):
        event_id = str((params or {}).get('event'))
        calls.append(event_id)
        return {'id': event_id, 'header': {'competitions': []}}

    monkeypatch.setattr(provider, '_fetch_json', _mock_fetch)

    provider.fetch_raw('evt-1')
    provider.fetch_raw('evt-1')
    provider.fetch_raw('evt-2')

    assert calls == ['evt-1', 'evt-2']


def test_play_by_play_provider_cache_hit_and_miss(monkeypatch) -> None:
    from app.services.play_by_play_provider import ESPNPlayByPlayProvider

    provider = ESPNPlayByPlayProvider()
    calls: list[str] = []

    def _mock_fetch(url: str, params: dict[str, str] | None = None):
        event_id = str((params or {}).get('event'))
        calls.append(event_id)
        return {
            'id': event_id,
            'plays': [
                {
                    'type': 'shot',
                    'text': 'Nikola Jokic makes two point shot',
                    'period': {'number': 1},
                    'clock': {'displayValue': '10:10'},
                    'team': {'displayName': 'Denver Nuggets'},
                    'athletesInvolved': [{'athlete': {'displayName': 'Nikola Jokic'}}],
                    'scoringPlay': True,
                }
            ],
        }

    monkeypatch.setattr(provider, '_fetch_json', _mock_fetch)

    assert provider.get_normalized_events('evt-1') is not None
    assert provider.get_normalized_events('evt-1') is not None
    assert provider.get_normalized_events('evt-2') is not None

    assert calls == ['evt-1', 'evt-2']
