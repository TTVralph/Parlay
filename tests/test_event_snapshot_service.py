from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.grader import grade_text
from app.providers.base import EventInfo
from app.providers.espn_provider import ESPNNBAResultsProvider
from app.services.event_snapshot import EventSnapshot, EventSnapshotService
from app.services.play_by_play_provider import PlayByPlayEvent
from app.services.request_cache import RequestCache
from app.services.snapshot_store import SnapshotStore


class _FakeScoreboardProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_events_for_date(self, date_str: str) -> list[dict[str, Any]]:
        self.calls.append(date_str)
        return [
            {
                'event_id': 'evt-1',
                'date': '2026-03-06T00:30:00Z',
                'status': 'final',
                'home_team': 'Denver Nuggets',
                'away_team': 'Boston Celtics',
            }
        ]


class _FakeGamecastProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_normalized(self, event_id: str) -> dict[str, Any] | None:
        self.calls.append(event_id)
        return {
            'event_id': event_id,
            'status': {'state': 'post'},
            'raw': {
                'header': {
                    'competitions': [
                        {
                            'date': '2026-03-06T00:30:00Z',
                            'competitors': [
                                {'homeAway': 'home', 'score': '110', 'team': {'id': '7', 'displayName': 'Denver Nuggets', 'abbreviation': 'DEN'}},
                                {'homeAway': 'away', 'score': '101', 'team': {'id': '2', 'displayName': 'Boston Celtics', 'abbreviation': 'BOS'}},
                            ],
                        }
                    ]
                },
                'boxscore': {
                    'players': [
                        {
                            'team': {'displayName': 'Denver Nuggets'},
                            'statistics': [
                                {
                                    'labels': ['PTS', 'REB', 'AST'],
                                    'athletes': [
                                        {
                                            'athlete': {'id': '15', 'displayName': 'Nikola Jokic'},
                                            'stats': ['30', '12', '10'],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            },
        }


class _FakePlayByPlayProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_normalized_events(self, event_id: str) -> list[PlayByPlayEvent] | None:
        self.calls.append(event_id)
        return [
            PlayByPlayEvent(
                event_order=0,
                event_type='shot',
                description='Nikola Jokic makes two point shot',
                period=1,
                clock='11:45',
                team='Denver Nuggets',
                primary_player='Nikola Jokic',
                is_scoring_play=True,
                is_made_shot=True,
            )
        ]


def test_event_snapshot_is_built_once_and_reused_for_same_event() -> None:
    scoreboard = _FakeScoreboardProvider()
    gamecast = _FakeGamecastProvider()
    service = EventSnapshotService(scoreboard_provider=scoreboard, gamecast_provider=gamecast, play_by_play_provider=_FakePlayByPlayProvider())

    first = service.get_event_snapshot('evt-1', event_date='2026-03-06')
    second = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert first is second
    assert gamecast.calls == ['evt-1']
    assert scoreboard.calls == ['2026-03-06']
    player = first.normalized_player_stats['nikolajokic']
    assert player['stats']['PRA'] == 52.0
    assert player['stats']['PR'] == 42.0
    assert player['stats']['RA'] == 22.0
    coverage = first.get_stat_coverage()
    assert coverage['players'] == 1
    assert 'PTS' in coverage['stat_keys']
    assert coverage['snapshot_source'] == 'summary+boxscore'


def test_event_snapshot_play_by_play_enrichment_is_lazy_and_cached(tmp_path) -> None:
    pbp = _FakePlayByPlayProvider()
    service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeGamecastProvider(),
        play_by_play_provider=pbp,
        snapshot_store=SnapshotStore(base_dir=tmp_path / 'snapshots'),
    )

    first = service.get_event_snapshot('evt-1')
    assert first is not None
    assert first.normalized_play_by_play is None

    enriched = service.get_event_snapshot('evt-1', include_play_by_play=True)
    assert enriched is first
    assert enriched.normalized_play_by_play is not None
    assert pbp.calls == ['evt-1']


def test_request_cache_hit_miss_behavior_still_works_with_snapshot_service(monkeypatch, tmp_path) -> None:
    from app.services.gamecast_provider import ESPNGamecastProvider

    calls: list[str] = []
    gamecast = ESPNGamecastProvider(cache=RequestCache(max_entries=8))

    def _mock_fetch(url: str, params: dict[str, str] | None = None):
        event_id = str((params or {}).get('event'))
        calls.append(event_id)
        return {'id': event_id, 'header': {'competitions': []}, 'boxscore': {'players': []}}

    monkeypatch.setattr(gamecast, '_fetch_json', _mock_fetch)

    service = EventSnapshotService(gamecast_provider=gamecast, snapshot_store=SnapshotStore(base_dir=tmp_path / "snapshots"))
    service.get_event_snapshot('evt-1')
    service.get_event_snapshot('evt-1')
    service.get_event_snapshot('evt-2')

    assert calls == ['evt-1', 'evt-2']


class _FakeESPNProvider(ESPNNBAResultsProvider):
    def __init__(self) -> None:
        super().__init__()
        self.player_result_calls = 0
        self.player_result_detail_calls = 0
        self._event = EventInfo(
            event_id='evt-1',
            sport='NBA',
            home_team='Denver Nuggets',
            away_team='Boston Celtics',
            start_time=datetime(2026, 3, 6, tzinfo=timezone.utc),
        )

    def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False) -> list[EventInfo]:
        return [self._event]

    def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False) -> list[EventInfo]:
        return [self._event]

    def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False) -> str | None:
        return 'Denver Nuggets'

    def get_event_info(self, event_id: str):
        return {'home_team': 'Denver Nuggets', 'away_team': 'Boston Celtics'}

    def get_event_status(self, event_id: str) -> str | None:
        return 'final'

    def is_player_on_event_roster(self, player: str, event_id: str | None = None) -> bool | None:
        return True

    def get_player_result_details(self, player: str, market_type: str, event_id: str | None = None) -> dict[str, Any] | None:
        self.player_result_detail_calls += 1
        value = self.get_player_result(player, market_type, event_id)
        if value is None:
            return None
        return {'actual_value': value, 'matched_boxscore_player_name': 'Nikola Jokic'}

    def get_player_result(self, player: str, market_type: str, event_id: str | None = None) -> float | None:
        self.player_result_calls += 1
        if market_type == 'player_points':
            return 31.0
        if market_type == 'player_assists':
            return 9.0
        if market_type == 'player_rebounds':
            return 12.0
        return None


def test_grading_groups_legs_by_event_and_builds_snapshot_once(monkeypatch) -> None:
    calls: list[str] = []

    class _CountingSnapshotService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_many_event_snapshots(self, event_ids, *, event_dates=None, include_play_by_play_event_ids=None):
            calls.extend(event_ids)
            return {
                event_id: EventSnapshot(
                    event_id=event_id,
                    home_team={'name': 'Denver Nuggets'},
                    away_team={'name': 'Boston Celtics'},
                )
                for event_id in event_ids
            }

    monkeypatch.setattr('app.grader.EventSnapshotService', _CountingSnapshotService)

    provider = _FakeESPNProvider()
    result = grade_text('Nikola Jokic over 29.5 points\nNikola Jokic over 7.5 assists', provider=provider)

    assert len(result.legs) == 2
    assert calls == ['evt-1']




def test_snapshot_native_grading_uses_snapshot_before_provider(monkeypatch) -> None:
    class _SnapshotService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_many_event_snapshots(self, event_ids, *, event_dates=None, include_play_by_play_event_ids=None):
            return {
                event_id: EventSnapshot(
                    event_id=event_id,
                    home_team={'name': 'Denver Nuggets'},
                    away_team={'name': 'Boston Celtics'},
                    normalized_player_stats={
                        'nikolajokic': {
                            'player_id': '15',
                            'display_name': 'Nikola Jokic',
                            'stats': {'PTS': 31.0, 'REB': 12.0, 'AST': 9.0, '3PM': 3.0, 'STL': 2.0, 'BLK': 2.0, 'TOV': 3.0, 'PR': 43.0, 'PA': 40.0, 'RA': 21.0, 'PRA': 52.0},
                        }
                    },
                )
                for event_id in event_ids
            }

    monkeypatch.setattr('app.grader.EventSnapshotService', _SnapshotService)

    provider = _FakeESPNProvider()
    result = grade_text(
        'Nikola Jokic over 29.5 points\nNikola Jokic over 2.5 threes\nNikola Jokic over 39.5 pa',
        provider=provider,
    )

    assert [leg.settlement for leg in result.legs] == ['win', 'win', 'win']
    assert provider.player_result_calls == 0
    assert provider.player_result_detail_calls == 0
    snapshot_run_diag = result.grading_diagnostics.get('snapshot') or {}
    assert snapshot_run_diag.get('snapshot_stats_used') == 3
    assert snapshot_run_diag.get('provider_fallbacks') == 0


def test_snapshot_fallback_keeps_provider_behavior_when_stat_missing(monkeypatch) -> None:
    class _SnapshotService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_many_event_snapshots(self, event_ids, *, event_dates=None, include_play_by_play_event_ids=None):
            return {
                event_id: EventSnapshot(
                    event_id=event_id,
                    home_team={'name': 'Denver Nuggets'},
                    away_team={'name': 'Boston Celtics'},
                    normalized_player_stats={
                        'nikolajokic': {
                            'player_id': '15',
                            'display_name': 'Nikola Jokic',
                            'stats': {'REB': 12.0, 'AST': 9.0},
                        }
                    },
                )
                for event_id in event_ids
            }

    monkeypatch.setattr('app.grader.EventSnapshotService', _SnapshotService)

    provider = _FakeESPNProvider()
    result = grade_text('Nikola Jokic over 29.5 points\nNikola Jokic over 2.5 threes', provider=provider)

    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement in {'unmatched', 'pending'}
    assert provider.player_result_calls > 0
    first_leg_diag = result.legs[0].settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    second_leg_diag = result.legs[1].settlement_diagnostics.get('snapshot_stat_diagnostics') or {}
    assert first_leg_diag.get('provider_fallback_used') is True
    assert second_leg_diag.get('provider_fallback_used') is True
    snapshot_run_diag = result.grading_diagnostics.get('snapshot') or {}
    assert snapshot_run_diag.get('provider_fallbacks') == 2
    assert snapshot_run_diag.get('missing_snapshot_keys')

def test_non_espn_provider_path_is_unchanged_without_snapshot() -> None:
    class _NonEspnProvider:
        def resolve_team_event(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
            return None

        def resolve_player_event(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            return EventInfo(
                event_id='other-1',
                sport='NBA',
                home_team='Home',
                away_team='Away',
                start_time=datetime(2026, 3, 6, tzinfo=timezone.utc),
            )

        def resolve_team_event_candidates(self, team: str, as_of: datetime | None, *, include_historical: bool = False):
            return []

        def resolve_player_event_candidates(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            return [self.resolve_player_event(player, as_of)]

        def get_team_result(self, team: str, event_id: str | None = None):
            return None

        def get_player_result(self, player: str, market_type: str, event_id: str | None = None):
            return 31.0 if market_type == 'player_points' else None

        def did_player_appear(self, player: str, event_id: str | None = None):
            return True

        def resolve_player_team(self, player: str, as_of: datetime | None, *, include_historical: bool = False):
            return 'Home'

        def get_event_info(self, event_id: str):
            return {'home_team': 'Home', 'away_team': 'Away'}

        def is_player_on_event_roster(self, player: str, event_id: str | None = None):
            return True

        def get_event_status(self, event_id: str):
            return 'final'

    result = grade_text('Nikola Jokic over 29.5 points', provider=_NonEspnProvider())
    assert result.legs[0].settlement == 'win'


class _FakeFinalGamecastProvider(_FakeGamecastProvider):
    def fetch_normalized(self, event_id: str) -> dict[str, Any] | None:
        payload = super().fetch_normalized(event_id)
        if payload is None:
            return None
        payload['status'] = {'state': 'final'}
        return payload


class _FakeLiveGamecastProvider(_FakeGamecastProvider):
    def fetch_normalized(self, event_id: str) -> dict[str, Any] | None:
        payload = super().fetch_normalized(event_id)
        if payload is None:
            return None
        payload['status'] = {'state': 'in_progress'}
        return payload


class _FakeScheduledGamecastProvider(_FakeGamecastProvider):
    def fetch_normalized(self, event_id: str) -> dict[str, Any] | None:
        payload = super().fetch_normalized(event_id)
        if payload is None:
            return None
        payload['status'] = {'state': 'scheduled'}
        return payload


class _FakeNonFinalScoreboardProvider(_FakeScoreboardProvider):
    def fetch_events_for_date(self, date_str: str) -> list[dict[str, Any]]:
        rows = super().fetch_events_for_date(date_str)
        rows[0]['status'] = 'in_progress'
        return rows


def test_snapshot_saved_after_build_for_final_game(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeFinalGamecastProvider(),
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert store.snapshot_exists('evt-1') is True
    raw = (tmp_path / 'snapshots' / 'evt-1.json').read_text(encoding='utf-8')
    assert 'normalized_player_stats' in raw
    assert 'normalized_team_stats' in raw
    assert 'metadata' in raw
    assert 'diagnostics' in raw


def test_snapshot_reused_from_store_without_provider_calls(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    first_service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeFinalGamecastProvider(),
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )
    first_service.get_event_snapshot('evt-1', event_date='2026-03-06')

    scoreboard = _FakeScoreboardProvider()
    gamecast = _FakeFinalGamecastProvider()
    second_service = EventSnapshotService(
        scoreboard_provider=scoreboard,
        gamecast_provider=gamecast,
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = second_service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert snapshot.event_id == 'evt-1'
    assert gamecast.calls == []
    assert scoreboard.calls == ['2026-03-06']
    assert snapshot.snapshot_origin == 'persisted'


def test_snapshot_store_corruption_falls_back_to_provider(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    (tmp_path / 'snapshots').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'snapshots' / 'evt-1.json').write_text('{bad json', encoding='utf-8')

    scoreboard = _FakeScoreboardProvider()
    gamecast = _FakeFinalGamecastProvider()
    service = EventSnapshotService(
        scoreboard_provider=scoreboard,
        gamecast_provider=gamecast,
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert gamecast.calls == ['evt-1']
    assert scoreboard.calls == ['2026-03-06']


def test_snapshot_store_missing_file_falls_back_to_provider(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    scoreboard = _FakeScoreboardProvider()
    gamecast = _FakeFinalGamecastProvider()
    service = EventSnapshotService(
        scoreboard_provider=scoreboard,
        gamecast_provider=gamecast,
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert gamecast.calls == ['evt-1']
    assert scoreboard.calls == ['2026-03-06']


def test_live_snapshot_is_not_persisted(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeLiveGamecastProvider(),
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert snapshot.snapshot_origin == 'rebuilt'
    assert store.snapshot_exists('evt-1') is False


def test_scheduled_snapshot_is_not_persisted(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeScheduledGamecastProvider(),
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert store.snapshot_exists('evt-1') is False


def test_stale_in_memory_live_snapshot_rebuilds(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    gamecast = _FakeLiveGamecastProvider()
    service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=gamecast,
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
        live_freshness_seconds=15,
    )

    first = service.get_event_snapshot('evt-1', event_date='2026-03-06')
    assert first is not None
    first.built_at = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    first.diagnostics.built_at = first.built_at

    second = service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert second is not None
    assert second is not first
    assert len(gamecast.calls) == 2


def test_persisted_final_snapshot_with_non_final_scoreboard_status_rebuilds(tmp_path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    first_service = EventSnapshotService(
        scoreboard_provider=_FakeScoreboardProvider(),
        gamecast_provider=_FakeFinalGamecastProvider(),
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )
    first_service.get_event_snapshot('evt-1', event_date='2026-03-06')

    scoreboard = _FakeNonFinalScoreboardProvider()
    gamecast = _FakeLiveGamecastProvider()
    second_service = EventSnapshotService(
        scoreboard_provider=scoreboard,
        gamecast_provider=gamecast,
        play_by_play_provider=_FakePlayByPlayProvider(),
        snapshot_store=store,
    )

    snapshot = second_service.get_event_snapshot('evt-1', event_date='2026-03-06')

    assert snapshot is not None
    assert snapshot.snapshot_origin == 'rebuilt'
    assert gamecast.calls == ['evt-1']


def test_snapshot_readiness_details_include_derived_market_metadata(monkeypatch) -> None:
    class _SnapshotService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_many_event_snapshots(self, event_ids, *, event_dates=None, include_play_by_play_event_ids=None):
            return {
                event_id: EventSnapshot(
                    event_id=event_id,
                    home_team={'name': 'Denver Nuggets'},
                    away_team={'name': 'Boston Celtics'},
                    normalized_player_stats={
                        'nikolajokic': {
                            'player_id': '15',
                            'display_name': 'Nikola Jokic',
                            'stats': {'PTS': 31.0, 'REB': 12.0, 'AST': 10.0, 'STL': 2.0, 'BLK': 1.0},
                        }
                    },
                )
                for event_id in event_ids
            }

    monkeypatch.setattr('app.grader.EventSnapshotService', _SnapshotService)

    provider = _FakeESPNProvider()
    result = grade_text('Nikola Jokic double double yes', provider=provider)

    assert result.legs[0].settlement == 'win'
    snapshot_run_diag = result.grading_diagnostics.get('snapshot') or {}
    assert snapshot_run_diag.get('snapshot_stats_used') == 1
    details = snapshot_run_diag.get('market_snapshot_details') or []
    assert details
    first = details[0]
    assert first.get('market_type') == 'player_double_double'
    assert first.get('snapshot_used') is True
    assert first.get('provider_fallback') is False
    assert first.get('required_component_stat_keys') == ['PTS', 'REB', 'AST', 'STL', 'BLK']
    assert first.get('player_match_result') == 'matched'
