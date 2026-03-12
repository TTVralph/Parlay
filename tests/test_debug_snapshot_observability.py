from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.debug_observability import get_debug_observability_service
from app.services.snapshot_hydrator import SnapshotHydrator
from app.services.snapshot_store import SnapshotStore


client = TestClient(app)


def _reset_observability() -> None:
    service = get_debug_observability_service()
    service._grading_history.clear()  # noqa: SLF001
    service._hydration_history.clear()  # noqa: SLF001
    service._latest_hydration_summary = None  # noqa: SLF001


def _admin_headers() -> dict[str, str]:
    login = client.post('/admin/auth/login', json={'username': 'admin-observability', 'password': 'secret123'})
    assert login.status_code == 200
    return {'Authorization': f"Bearer {login.json()['access_token']}"}


class _FakeSnapshotStore:
    def load_snapshot(self, event_id: str):
        return None


class _FakeSnapshot:
    snapshot_origin = 'built'


class _FakeEventSnapshotService:
    def __init__(self) -> None:
        self._snapshots: dict[str, object] = {}
        self._snapshot_store = _FakeSnapshotStore()

    def is_snapshot_fresh(self, snapshot: object, event_status: str | None) -> bool:
        return False

    def get_event_snapshot(self, event_id: str, event_date: str | None = None):
        return _FakeSnapshot()

    def should_persist_snapshot(self, snapshot: object) -> bool:
        return True


class _FakeDailyManifestService:
    def get_daily_manifest(self, sport: str, date_value: str):
        return {'date': str(date_value), 'events': [{'event_id': 'evt-1', 'game_status': 'Final'}]}


def test_admin_debug_snapshots_endpoint_exposes_expected_keys(monkeypatch) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')

    service = get_debug_observability_service()
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 1, 'provider_fallbacks': 0, 'missing_snapshot_keys': ['points'], 'players_missing_stats': ['Jokic']}})

    response = client.get('/admin/debug/snapshots', headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()

    assert 'snapshot_stats_used' in body
    assert 'provider_fallbacks' in body
    assert 'missing_snapshot_keys' in body
    assert 'players_missing_stats' in body
    assert 'recent_hydration_summary' in body
    assert 'snapshot_store' in body
    assert body['missing_snapshot_keys']['points'] == 1
    assert body['players_missing_stats']['Jokic'] == 1


def test_grading_run_updates_observability(monkeypatch) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')

    grade_response = client.post('/grade', json={'text': 'Nikola Jokic over 0.5 points'})
    assert grade_response.status_code == 200

    debug_response = client.get('/admin/debug/snapshots', headers=_admin_headers())
    assert debug_response.status_code == 200
    payload = debug_response.json()
    assert payload['recent_grading_runs_count'] >= 1


def test_hydration_run_updates_observability(monkeypatch, tmp_path: Path) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')

    hydrator = SnapshotHydrator(
        daily_manifest_service=_FakeDailyManifestService(),
        event_snapshot_service=_FakeEventSnapshotService(),
    )
    summary = hydrator.hydrate_date('NBA', '2026-03-06')
    assert summary['events_seen'] == 1

    debug_response = client.get('/admin/debug/snapshots', headers=_admin_headers())
    assert debug_response.status_code == 200
    payload = debug_response.json()
    assert payload['recent_hydration_summary'] is not None
    assert payload['recent_hydration_summary']['summary']['events_seen'] == 1


def test_observability_history_is_bounded(tmp_path: Path) -> None:
    store = SnapshotStore(base_dir=tmp_path / 'snapshots')
    service = get_debug_observability_service().__class__(max_grading_history=3, max_hydration_history=2, snapshot_store=store)

    for idx in range(10):
        service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': idx + 1, 'provider_fallbacks': 0, 'missing_snapshot_keys': [], 'players_missing_stats': []}})
    for idx in range(5):
        service.record_hydration_summary({'events_seen': idx + 1})

    payload = service.get_observability_snapshot()
    assert payload['recent_grading_runs_count'] == 3
    assert payload['recent_hydration_runs_count'] == 2
