from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Lock
from typing import Any

from app.services.snapshot_store import SnapshotStore


class DebugObservabilityService:
    """In-memory aggregation for grading/snapshot/hydration diagnostics."""

    def __init__(
        self,
        *,
        max_grading_history: int = 50,
        max_hydration_history: int = 20,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._max_grading_history = max(1, int(max_grading_history))
        self._max_hydration_history = max(1, int(max_hydration_history))
        self._grading_history: deque[dict[str, Any]] = deque(maxlen=self._max_grading_history)
        self._hydration_history: deque[dict[str, Any]] = deque(maxlen=self._max_hydration_history)
        self._latest_hydration_summary: dict[str, Any] | None = None
        self._snapshot_store = snapshot_store or SnapshotStore()
        self._lock = Lock()

    def record_grading_diagnostics(self, grading_diagnostics: dict[str, Any] | None) -> None:
        snapshot_diag = dict((grading_diagnostics or {}).get('snapshot') or {})
        if not snapshot_diag:
            return
        snapshot_diag['recorded_at'] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._grading_history.append(snapshot_diag)

    def record_hydration_summary(self, hydration_summary: dict[str, Any] | None) -> None:
        summary = dict(hydration_summary or {})
        if not summary:
            return
        entry = {
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'summary': summary,
        }
        with self._lock:
            self._latest_hydration_summary = entry
            self._hydration_history.append(entry)

    def _snapshot_store_stats(self) -> dict[str, Any]:
        snapshot_dir = Path(self._snapshot_store._base_dir)  # noqa: SLF001
        persisted_files = 0
        if snapshot_dir.exists() and snapshot_dir.is_dir():
            persisted_files = sum(1 for path in snapshot_dir.glob('*.json') if path.is_file())
        return {
            'snapshot_dir': str(snapshot_dir),
            'persisted_files': persisted_files,
        }

    def _aggregate_grading_history(self) -> dict[str, Any]:
        snapshot_stats_used = 0
        provider_fallbacks = 0
        missing_snapshot_keys: Counter[str] = Counter()
        players_missing_stats: Counter[str] = Counter()

        recent = [deepcopy(item) for item in self._grading_history]
        for entry in recent:
            snapshot_stats_used += int(entry.get('snapshot_stats_used') or 0)
            provider_fallbacks += int(entry.get('provider_fallbacks') or 0)
            for key in entry.get('missing_snapshot_keys') or []:
                missing_snapshot_keys[str(key)] += 1
            for player in entry.get('players_missing_stats') or []:
                players_missing_stats[str(player)] += 1

        return {
            'snapshot_stats_used': snapshot_stats_used,
            'provider_fallbacks': provider_fallbacks,
            'missing_snapshot_keys': dict(sorted(missing_snapshot_keys.items())),
            'players_missing_stats': dict(sorted(players_missing_stats.items())),
            'recent_grading_runs': recent,
            'recent_grading_runs_count': len(recent),
            'max_grading_history': self._max_grading_history,
        }

    def get_observability_snapshot(self) -> dict[str, Any]:
        with self._lock:
            grading = self._aggregate_grading_history()
            latest_hydration = deepcopy(self._latest_hydration_summary)
            hydration_history = [deepcopy(item) for item in self._hydration_history]

        return {
            **grading,
            'recent_hydration_summary': latest_hydration,
            'recent_hydration_runs': hydration_history,
            'recent_hydration_runs_count': len(hydration_history),
            'max_hydration_history': self._max_hydration_history,
            'snapshot_store': self._snapshot_store_stats(),
        }


def debug_observability_enabled() -> bool:
    explicit = os.getenv('PARLAY_ENABLE_DEBUG_OBSERVABILITY', '').strip().lower()
    if explicit in {'1', 'true', 'yes', 'on'}:
        return True
    if explicit in {'0', 'false', 'no', 'off'}:
        return False

    environment = (
        os.getenv('PARLAY_ENV')
        or os.getenv('APP_ENV')
        or os.getenv('ENV')
        or os.getenv('FASTAPI_ENV')
        or ''
    ).strip().lower()
    return environment in {'dev', 'development', 'local', 'test', 'testing'}


_DEBUG_OBSERVABILITY = DebugObservabilityService()


def get_debug_observability_service() -> DebugObservabilityService:
    return _DEBUG_OBSERVABILITY
