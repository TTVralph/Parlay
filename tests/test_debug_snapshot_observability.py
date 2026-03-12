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


def test_hydration_candidates_prioritize_event_ids_and_dedupe() -> None:
    service = get_debug_observability_service().__class__(max_grading_history=10, max_hydration_history=5, snapshot_store=SnapshotStore(base_dir=Path('tmp-snapshot-test')))
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 1, 'provider_fallbacks': 3, 'missing_snapshot_keys': ['STL', 'BLK'], 'players_missing_stats': ['A'], 'event_ids': ['401', '401'], 'bet_dates': ['2026-03-06'], 'sports': ['NBA'], 'leagues': ['NBA']}})
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 0, 'provider_fallbacks': 2, 'missing_snapshot_keys': ['STL'], 'players_missing_stats': ['B'], 'event_ids': ['402'], 'bet_dates': ['2026-03-06'], 'sports': ['NBA'], 'leagues': ['NBA']}})
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 0, 'provider_fallbacks': 1, 'missing_snapshot_keys': ['AST'], 'players_missing_stats': ['C'], 'event_ids': [], 'bet_dates': ['2026-03-07'], 'sports': ['NBA'], 'leagues': ['NBA']}})

    candidates = service.get_hydration_candidates_from_observability(max_event_ids=5, max_dates=5)

    assert candidates['event_ids'][:2] == ['401', '402']
    assert candidates['dates'] == ['2026-03-07']
    assert candidates['reasons']['event_401']['provider_fallbacks'] == 3
    assert sorted(candidates['reasons']['event_401']['missing_snapshot_keys']) == ['BLK', 'STL']


def test_hydration_candidates_endpoint_shape(monkeypatch) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')
    service = get_debug_observability_service()
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 0, 'provider_fallbacks': 2, 'missing_snapshot_keys': ['STL'], 'players_missing_stats': [], 'event_ids': ['401'], 'bet_dates': ['2026-03-06'], 'sports': ['NBA'], 'leagues': ['NBA']}})

    response = client.get('/admin/debug/hydration-candidates', headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {'event_ids', 'dates', 'reasons', 'limits'}
    assert 'event_401' in body['reasons']


def test_hydrate_hotspots_endpoint_records_summary(monkeypatch) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')
    service = get_debug_observability_service()
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 0, 'provider_fallbacks': 2, 'missing_snapshot_keys': ['STL'], 'players_missing_stats': [], 'event_ids': ['evt-1'], 'bet_dates': ['2026-03-06'], 'sports': ['NBA'], 'leagues': ['NBA']}})

    class _EndpointHydrator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def hydrate_observed_hotspots(self, **kwargs):
            return {'events_seen': 1, 'snapshots_built': 1, 'snapshots_reused': 0, 'snapshots_persisted': 1, 'skipped_stale_or_unneeded': 0, 'errors': 0, 'trigger': 'observability_hotspots', 'candidates_used': {'event_ids': ['evt-1'], 'dates': []}}

    monkeypatch.setattr('app.main.SnapshotHydrator', _EndpointHydrator)

    response = client.post('/admin/debug/hydrate-hotspots', headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert body['trigger'] == 'observability_hotspots'



def test_market_readiness_report_classifies_markets() -> None:
    service = get_debug_observability_service().__class__(
        max_grading_history=50,
        max_hydration_history=5,
        snapshot_store=SnapshotStore(base_dir=Path('tmp-snapshot-test')),
        readiness_min_samples=4,
        readiness_ready_fallback_rate=0.15,
        readiness_not_ready_fallback_rate=0.5,
    )

    for idx in range(5):
        service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 1, 'provider_fallbacks': 0, 'missing_snapshot_keys': [], 'players_missing_stats': [], 'market_snapshot_details': [{'market_type': 'player_points', 'stat_family': 'PTS', 'used_snapshot': True, 'provider_fallback_used': False, 'requested_stat_key': 'PTS', 'player_id_resolved': True, 'player_snapshot_found': True, 'missing_snapshot_stat_key': None, 'event_id': f'e-{idx}', 'sport': 'NBA', 'league': 'NBA'}]}})

    for idx in range(4):
        service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 0, 'provider_fallbacks': 1, 'missing_snapshot_keys': ['STL'], 'players_missing_stats': [], 'market_snapshot_details': [{'market_type': 'player_steals', 'stat_family': 'STL', 'used_snapshot': False, 'provider_fallback_used': True, 'requested_stat_key': 'STL', 'player_id_resolved': True, 'player_snapshot_found': idx % 2 == 0, 'missing_snapshot_stat_key': 'STL', 'event_id': f's-{idx}', 'sport': 'NBA', 'league': 'NBA'}]}})

    report = service.get_snapshot_market_coverage_report()

    points = report['markets']['player_points']
    steals = report['markets']['player_steals']
    assert points['status'] == 'ready'
    assert points['runs'] == 5
    assert points['fallback_rate'] == 0.0
    assert steals['status'] == 'not_ready'
    assert steals['provider_fallbacks'] == 4
    assert steals['missing_snapshot_keys']['STL'] == 4


def test_market_readiness_report_handles_low_sample_market() -> None:
    service = get_debug_observability_service().__class__(
        max_grading_history=10,
        max_hydration_history=5,
        snapshot_store=SnapshotStore(base_dir=Path('tmp-snapshot-test')),
        readiness_min_samples=5,
    )
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 1, 'provider_fallbacks': 0, 'missing_snapshot_keys': [], 'players_missing_stats': [], 'market_snapshot_details': [{'market_type': 'player_blocks', 'stat_family': 'BLK', 'used_snapshot': True, 'provider_fallback_used': False, 'requested_stat_key': 'BLK', 'player_id_resolved': True, 'player_snapshot_found': True, 'missing_snapshot_stat_key': None, 'event_id': 'blk-1', 'sport': 'NBA', 'league': 'NBA'}]}})

    report = service.get_snapshot_market_coverage_report()
    blocks = report['markets']['player_blocks']
    assert blocks['status'] == 'partial'
    assert blocks['runs'] == 1


def test_market_readiness_endpoint_shape(monkeypatch) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')
    service = get_debug_observability_service()
    service.record_grading_diagnostics({'snapshot': {'snapshot_stats_used': 1, 'provider_fallbacks': 0, 'missing_snapshot_keys': [], 'players_missing_stats': [], 'market_snapshot_details': [{'market_type': 'player_points', 'stat_family': 'PTS', 'used_snapshot': True, 'provider_fallback_used': False, 'requested_stat_key': 'PTS', 'player_id_resolved': True, 'player_snapshot_found': True, 'missing_snapshot_stat_key': None, 'event_id': '401', 'sport': 'NBA', 'league': 'NBA'}]}})

    response = client.get('/admin/debug/market-readiness', headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {'markets', 'thresholds', 'recent_grading_runs_count'}
    assert 'player_points' in body['markets']
    assert set(body['markets']['player_points'].keys()) >= {'runs', 'snapshot_successes', 'provider_fallbacks', 'fallback_rate', 'missing_snapshot_keys', 'players_missing_stats', 'status'}


def test_period_snapshot_availability_report_shape(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / 'snapshots'
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / 'evt-1.json').write_text(
        '{"event_id":"evt-1","normalized_period_results":[{"period_number":1,"period_label":"Q1","is_score_complete":true,"source":"summary_competitor_linescores"},{"period_number":2,"period_label":"Q2","is_score_complete":true,"source":"summary_competitor_linescores"},{"period_number":3,"period_label":"Q3","is_score_complete":true,"source":"summary_competitor_linescores"},{"period_number":4,"period_label":"Q4","is_score_complete":true,"source":"summary_competitor_linescores"}]}'
    )
    (snapshots_dir / 'evt-2.json').write_text(
        '{"event_id":"evt-2","normalized_period_results":[{"period_number":1,"period_label":"Q1","is_score_complete":true,"source":"summary_competitor_linescores"},{"period_number":2,"period_label":"Q2","is_score_complete":false,"source":"summary_competitor_linescores"}]}'
    )
    (snapshots_dir / 'evt-3.json').write_text('{"event_id":"evt-3","normalized_period_results":[]}')

    service = get_debug_observability_service().__class__(snapshot_store=SnapshotStore(base_dir=snapshots_dir))
    report = service.get_period_snapshot_availability_report(max_snapshots=10)

    assert set(report.keys()) >= {'totals', 'period_labels_available', 'period_extraction_sources', 'window'}
    assert report['totals']['events_with_period_data'] == 2
    assert report['totals']['events_with_complete_first_half'] == 1
    assert report['totals']['events_with_complete_quarters'] == 1
    assert report['totals']['events_with_missing_period_scoring'] == 1
    assert report['period_labels_available']['Q1'] == 2


def test_period_readiness_endpoint_shape(monkeypatch, tmp_path: Path) -> None:
    _reset_observability()
    monkeypatch.setenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '1')
    service = get_debug_observability_service()
    service._snapshot_store = SnapshotStore(base_dir=tmp_path / 'snapshots')  # noqa: SLF001

    snapshot_path = tmp_path / 'snapshots' / 'evt-1.json'
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text('{"event_id":"evt-1","normalized_period_results":[{"period_number":1,"period_label":"Q1","is_score_complete":true,"source":"summary_competitor_linescores"},{"period_number":2,"period_label":"Q2","is_score_complete":true,"source":"summary_competitor_linescores"}]}')

    response = client.get('/admin/debug/period-readiness', headers=_admin_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {'totals', 'period_labels_available', 'period_extraction_sources', 'window'}
