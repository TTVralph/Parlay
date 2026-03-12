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
        snapshot_diag['event_ids'] = sorted({str(v).strip() for v in snapshot_diag.get('event_ids') or [] if str(v).strip()})
        snapshot_diag['bet_dates'] = sorted({str(v).strip() for v in snapshot_diag.get('bet_dates') or [] if str(v).strip()})
        snapshot_diag['sports'] = sorted({str(v).strip() for v in snapshot_diag.get('sports') or [] if str(v).strip()})
        snapshot_diag['leagues'] = sorted({str(v).strip() for v in snapshot_diag.get('leagues') or [] if str(v).strip()})
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

    def get_hydration_candidates_from_observability(
        self,
        *,
        max_event_ids: int = 20,
        max_dates: int = 10,
    ) -> dict[str, Any]:
        with self._lock:
            recent = [deepcopy(item) for item in self._grading_history]

        event_scores: dict[str, dict[str, Any]] = {}
        date_scores: dict[str, dict[str, Any]] = {}

        for entry in recent:
            fallbacks = int(entry.get('provider_fallbacks') or 0)
            missing_keys = sorted({str(v) for v in (entry.get('missing_snapshot_keys') or []) if str(v).strip()})
            players_missing = sorted({str(v) for v in (entry.get('players_missing_stats') or []) if str(v).strip()})
            score = fallbacks + len(missing_keys) + len(players_missing)
            if score <= 0:
                continue

            context = {
                'provider_fallbacks': fallbacks,
                'missing_snapshot_keys': missing_keys,
                'players_missing_stats': players_missing,
                'sports': sorted({str(v) for v in (entry.get('sports') or []) if str(v).strip()}),
                'leagues': sorted({str(v) for v in (entry.get('leagues') or []) if str(v).strip()}),
            }

            for event_id in entry.get('event_ids') or []:
                normalized = str(event_id).strip()
                if not normalized:
                    continue
                bucket = event_scores.setdefault(normalized, {
                    'event_id': normalized,
                    'score': 0,
                    'provider_fallbacks': 0,
                    'missing_snapshot_keys': Counter(),
                    'players_missing_stats': Counter(),
                    'sports': set(),
                    'leagues': set(),
                })
                bucket['score'] += score
                bucket['provider_fallbacks'] += fallbacks
                for key in missing_keys:
                    bucket['missing_snapshot_keys'][key] += 1
                for player in players_missing:
                    bucket['players_missing_stats'][player] += 1
                bucket['sports'].update(context['sports'])
                bucket['leagues'].update(context['leagues'])

            run_has_event = bool(entry.get('event_ids'))
            for date_value in entry.get('bet_dates') or []:
                normalized_date = str(date_value).strip()
                if not normalized_date:
                    continue
                bucket = date_scores.setdefault(normalized_date, {
                    'date': normalized_date,
                    'score': 0,
                    'provider_fallbacks': 0,
                    'missing_snapshot_keys': Counter(),
                    'players_missing_stats': Counter(),
                    'sports': set(),
                    'leagues': set(),
                    'event_backed_score': 0,
                })
                bucket['score'] += score
                bucket['provider_fallbacks'] += fallbacks
                for key in missing_keys:
                    bucket['missing_snapshot_keys'][key] += 1
                for player in players_missing:
                    bucket['players_missing_stats'][player] += 1
                bucket['sports'].update(context['sports'])
                bucket['leagues'].update(context['leagues'])
                if run_has_event:
                    bucket['event_backed_score'] += score

        sorted_events = sorted(event_scores.values(), key=lambda row: (-row['score'], -row['provider_fallbacks'], row['event_id']))
        selected_events = [row['event_id'] for row in sorted_events[: max(1, int(max_event_ids))]]

        sorted_dates = sorted(
            date_scores.values(),
            key=lambda row: (-(row['score'] - row['event_backed_score']), -row['provider_fallbacks'], row['date']),
        )
        selected_dates = [row['date'] for row in sorted_dates if (row['score'] - row['event_backed_score']) > 0][: max(1, int(max_dates))]

        reasons: dict[str, Any] = {}
        for row in sorted_events[: max(1, int(max_event_ids))]:
            reasons[f"event_{row['event_id']}"] = {
                'provider_fallbacks': row['provider_fallbacks'],
                'missing_snapshot_keys': sorted(row['missing_snapshot_keys']),
                'players_missing_stats': sorted(row['players_missing_stats']),
                'sports': sorted(row['sports']),
                'leagues': sorted(row['leagues']),
                'score': row['score'],
            }
        for row in sorted_dates:
            if row['date'] not in selected_dates:
                continue
            reasons[f"date_{row['date']}"] = {
                'provider_fallbacks': row['provider_fallbacks'],
                'missing_snapshot_keys': sorted(row['missing_snapshot_keys']),
                'players_missing_stats': sorted(row['players_missing_stats']),
                'sports': sorted(row['sports']),
                'leagues': sorted(row['leagues']),
                'score': row['score'],
            }

        return {
            'event_ids': selected_events,
            'dates': selected_dates,
            'reasons': reasons,
            'limits': {
                'max_event_ids': max(1, int(max_event_ids)),
                'max_dates': max(1, int(max_dates)),
            },
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
