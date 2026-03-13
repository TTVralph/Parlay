from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time

from app.services.event_snapshot import EventSnapshot
from app.services.event_snapshot_cache import EventSnapshotCache


def _snapshot(*, event_id: str = 'evt-1', sport: str = 'NBA', status: str = 'in_progress', event_date: str | None = None) -> EventSnapshot:
    return EventSnapshot(
        event_id=event_id,
        sport=sport,
        event_status=status,
        event_date=event_date,
    )


def test_cache_hit_reuse() -> None:
    cache = EventSnapshotCache()
    calls = {'count': 0}

    def _fetcher() -> EventSnapshot:
        calls['count'] += 1
        return _snapshot(status='in_progress')

    first = cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)
    second = cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)

    assert first is second
    assert calls['count'] == 1
    stats = cache.get_stats()
    assert stats['snapshot_cache_hits'] == 1
    assert stats['snapshot_cache_misses'] == 1


def test_cache_expiration() -> None:
    now = [100.0]
    cache = EventSnapshotCache(now_fn=lambda: now[0])
    calls = {'count': 0}

    def _fetcher() -> EventSnapshot:
        calls['count'] += 1
        return _snapshot(status='in_progress')

    cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)
    now[0] += 31.0
    cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)

    assert calls['count'] == 2


def test_live_event_ttl_refresh() -> None:
    now = [100.0]
    cache = EventSnapshotCache(now_fn=lambda: now[0])

    cache.get_snapshot(
        sport='NBA',
        event_id='evt-1',
        include_play_by_play=False,
        fetcher=lambda: _snapshot(status='in_progress'),
    )
    assert cache.get_stats()['snapshot_cache_ttl'] == 30

    recent_date = (datetime.now(timezone.utc) - timedelta(hours=2)).date().isoformat()
    now[0] += 31.0
    cache.get_snapshot(
        sport='NBA',
        event_id='evt-1',
        include_play_by_play=False,
        fetcher=lambda: _snapshot(status='final', event_date=recent_date),
    )
    assert cache.get_stats()['snapshot_cache_ttl'] == 600

    historical_date = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    now[0] += 601.0
    cache.get_snapshot(
        sport='NBA',
        event_id='evt-1',
        include_play_by_play=False,
        fetcher=lambda: _snapshot(status='final', event_date=historical_date),
    )
    assert cache.get_stats()['snapshot_cache_ttl'] == 86400


def test_inflight_requests_are_deduplicated() -> None:
    cache = EventSnapshotCache()
    calls = {'count': 0}

    def _fetcher() -> EventSnapshot:
        calls['count'] += 1
        time.sleep(0.1)
        return _snapshot(status='in_progress')

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: cache.get_snapshot(
                    sport='NBA',
                    event_id='evt-1',
                    include_play_by_play=False,
                    fetcher=_fetcher,
                ),
                range(6),
            )
        )

    assert calls['count'] == 1
    assert len({id(item) for item in results}) == 1
    stats = cache.get_stats()
    assert stats['snapshot_cache_misses'] == 1
    assert stats['snapshot_cache_hits'] == 5


def test_cache_can_be_disabled_and_falls_back() -> None:
    cache = EventSnapshotCache(enabled=False)
    calls = {'count': 0}

    def _fetcher() -> EventSnapshot:
        calls['count'] += 1
        return _snapshot(status='in_progress')

    first = cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)
    second = cache.get_snapshot(sport='NBA', event_id='evt-1', include_play_by_play=False, fetcher=_fetcher)

    assert first is not None
    assert second is not None
    assert calls['count'] == 2
