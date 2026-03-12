from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.daily_event_manifest import DailyEventManifestService
from app.services.event_snapshot import EventSnapshotService
from app.services.snapshot_hydrator import SnapshotHydrator
from app.services.snapshot_store import SnapshotStore


class _HydrationScoreboardProvider:
    def __init__(self) -> None:
        self.fetch_raw_calls: list[str] = []
        self.fetch_events_calls: list[str] = []

    def fetch_raw(self, date_str: str) -> dict[str, Any]:
        self.fetch_raw_calls.append(date_str)
        return {
            'events': [
                {
                    'id': 'evt-final',
                    'date': '2026-03-06T01:00:00Z',
                    'shortName': 'BOS @ DEN',
                    'competitions': [
                        {
                            'status': {'type': {'state': 'post'}},
                            'competitors': [
                                {'homeAway': 'home', 'team': {'displayName': 'Denver Nuggets', 'abbreviation': 'DEN'}},
                                {'homeAway': 'away', 'team': {'displayName': 'Boston Celtics', 'abbreviation': 'BOS'}},
                            ],
                        }
                    ],
                },
                {
                    'id': 'evt-live',
                    'date': '2026-03-06T03:00:00Z',
                    'shortName': 'LAL @ PHX',
                    'competitions': [
                        {
                            'status': {'type': {'state': 'in'}},
                            'competitors': [
                                {'homeAway': 'home', 'team': {'displayName': 'Phoenix Suns', 'abbreviation': 'PHX'}},
                                {'homeAway': 'away', 'team': {'displayName': 'Los Angeles Lakers', 'abbreviation': 'LAL'}},
                            ],
                        }
                    ],
                },
                {
                    'id': 'evt-postponed',
                    'date': '2026-03-06T05:00:00Z',
                    'shortName': 'NYK @ MIA',
                    'competitions': [
                        {
                            'status': {'type': {'state': 'postponed'}},
                            'competitors': [
                                {'homeAway': 'home', 'team': {'displayName': 'Miami Heat', 'abbreviation': 'MIA'}},
                                {'homeAway': 'away', 'team': {'displayName': 'New York Knicks', 'abbreviation': 'NYK'}},
                            ],
                        }
                    ],
                },
            ]
        }

    def normalize_event(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        state = (((raw_event.get('competitions') or [{}])[0].get('status') or {}).get('type') or {}).get('state')
        competitors = ((raw_event.get('competitions') or [{}])[0].get('competitors') or [])
        home = next((team for team in competitors if team.get('homeAway') == 'home'), {})
        away = next((team for team in competitors if team.get('homeAway') == 'away'), {})
        return {
            'event_id': raw_event.get('id'),
            'date': raw_event.get('date'),
            'short_name': raw_event.get('shortName'),
            'home_team': (home.get('team') or {}).get('displayName'),
            'away_team': (away.get('team') or {}).get('displayName'),
            'home_team_abbr': (home.get('team') or {}).get('abbreviation'),
            'away_team_abbr': (away.get('team') or {}).get('abbreviation'),
            'competitors': [
                {'name': (home.get('team') or {}).get('displayName'), 'abbr': (home.get('team') or {}).get('abbreviation')},
                {'name': (away.get('team') or {}).get('displayName'), 'abbr': (away.get('team') or {}).get('abbreviation')},
            ],
            'status': state,
        }

    def fetch_events_for_date(self, date_str: str) -> list[dict[str, Any]]:
        self.fetch_events_calls.append(date_str)
        return [
            {'event_id': 'evt-final', 'status': 'final'},
            {'event_id': 'evt-live', 'status': 'in'},
            {'event_id': 'evt-postponed', 'status': 'postponed'},
            {'event_id': 'evt-corrupt', 'status': 'final'},
        ]


class _HydrationGamecastProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch_normalized(self, event_id: str) -> dict[str, Any]:
        self.calls.append(event_id)
        status_by_event = {
            'evt-final': 'final',
            'evt-live': 'in',
            'evt-postponed': 'postponed',
            'evt-corrupt': 'final',
        }
        state = status_by_event[event_id]
        return {
            'event_id': event_id,
            'status': {'state': state},
            'raw': {
                'header': {
                    'competitions': [
                        {
                            'date': '2026-03-06T02:00:00Z',
                            'competitors': [
                                {'homeAway': 'home', 'team': {'id': '1', 'displayName': 'Home', 'abbreviation': 'HME'}, 'score': '101'},
                                {'homeAway': 'away', 'team': {'id': '2', 'displayName': 'Away', 'abbreviation': 'AWY'}, 'score': '99'},
                            ],
                        }
                    ]
                },
                'boxscore': {'players': []},
            },
        }


def _build_hydrator(tmp_path: Path) -> tuple[SnapshotHydrator, _HydrationScoreboardProvider, _HydrationGamecastProvider, SnapshotStore]:
    scoreboard = _HydrationScoreboardProvider()
    gamecast = _HydrationGamecastProvider()
    snapshot_store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    snapshot_service = EventSnapshotService(
        scoreboard_provider=scoreboard,
        gamecast_provider=gamecast,
        snapshot_store=snapshot_store,
    )
    manifest_service = DailyEventManifestService(scoreboard_provider=scoreboard)
    hydrator = SnapshotHydrator(
        daily_manifest_service=manifest_service,
        event_snapshot_service=snapshot_service,
    )
    return hydrator, scoreboard, gamecast, snapshot_store


def test_hydrate_date_reuses_daily_manifest_cache(tmp_path: Path) -> None:
    hydrator, scoreboard, _, _ = _build_hydrator(tmp_path)

    hydrator.hydrate_date('NBA', '2026-03-06')
    hydrator.hydrate_date('NBA', '2026-03-06')

    assert scoreboard.fetch_raw_calls == ['2026-03-06']


def test_hydration_persists_final_but_not_live(tmp_path: Path) -> None:
    hydrator, _, _, store = _build_hydrator(tmp_path)

    summary = hydrator.hydrate_date('NBA', '2026-03-06')

    assert store.snapshot_exists('evt-final') is True
    assert store.snapshot_exists('evt-live') is False
    assert summary['snapshots_persisted'] == 1


def test_hydration_skips_rebuilding_fresh_snapshots(tmp_path: Path) -> None:
    hydrator, _, gamecast, _ = _build_hydrator(tmp_path)

    first = hydrator.hydrate_events(['evt-final'])
    second = hydrator.hydrate_events(['evt-final'])

    assert first['snapshots_built'] == 1
    assert second['snapshots_built'] == 0
    assert second['snapshots_reused'] == 1
    assert gamecast.calls == ['evt-final']


def test_corrupted_persisted_snapshot_falls_back_to_rebuild(tmp_path: Path) -> None:
    hydrator, _, gamecast, store = _build_hydrator(tmp_path)

    corrupt_path = tmp_path / 'snapshots' / 'evt-corrupt.json'
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text('{not-valid-json', encoding='utf-8')

    summary = hydrator.hydrate_events(['evt-corrupt'])

    assert summary['errors'] == 0
    assert summary['snapshots_built'] == 1
    assert store.snapshot_exists('evt-corrupt') is True
    persisted_payload = json.loads((tmp_path / 'snapshots' / 'evt-corrupt.json').read_text(encoding='utf-8'))
    assert persisted_payload['event_id'] == 'evt-corrupt'
    assert gamecast.calls == ['evt-corrupt']


def test_hydration_summary_counts_are_reported(tmp_path: Path) -> None:
    hydrator, _, _, _ = _build_hydrator(tmp_path)

    summary = hydrator.hydrate_date('NBA', '2026-03-06')

    assert summary == {
        'events_seen': 3,
        'snapshots_built': 2,
        'snapshots_reused': 0,
        'snapshots_persisted': 1,
        'skipped_stale_or_unneeded': 1,
        'errors': 0,
    }


class _FakeObservabilityForHotspots:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def get_hydration_candidates_from_observability(self, *, max_event_ids: int = 20, max_dates: int = 10) -> dict[str, Any]:
        return {
            'event_ids': ['evt-final', 'evt-final'],
            'dates': ['2026-03-08'],
            'reasons': {'date_2026-03-08': {'sports': ['NBA']}},
            'limits': {'max_event_ids': max_event_ids, 'max_dates': max_dates},
        }

    def record_hydration_summary(self, hydration_summary: dict[str, Any] | None) -> None:
        if hydration_summary:
            self.recorded.append(dict(hydration_summary))


def test_hydrate_observed_hotspots_prioritizes_events_and_records_summary(tmp_path: Path) -> None:
    hydrator, _, gamecast, _ = _build_hydrator(tmp_path)
    observability = _FakeObservabilityForHotspots()
    hydrator._observability_service = observability  # noqa: SLF001

    result = hydrator.hydrate_observed_hotspots(max_event_ids=3, max_dates=2)

    assert result['candidates_used']['event_ids'] == ['evt-final']
    assert result['target'] == 'events_then_dates'
    assert len(observability.recorded) == 1
    assert gamecast.calls[0] == 'evt-final'

