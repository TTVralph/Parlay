from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
import json
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
        readiness_min_samples: int = 10,
        readiness_ready_fallback_rate: float = 0.1,
        readiness_not_ready_fallback_rate: float = 0.35,
    ) -> None:
        self._max_grading_history = max(1, int(max_grading_history))
        self._max_hydration_history = max(1, int(max_hydration_history))
        self._readiness_min_samples = max(1, int(readiness_min_samples))
        self._readiness_ready_fallback_rate = max(0.0, min(1.0, float(readiness_ready_fallback_rate)))
        self._readiness_not_ready_fallback_rate = max(0.0, min(1.0, float(readiness_not_ready_fallback_rate)))
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

    @staticmethod
    def _label_is_quarter(label: str) -> bool:
        text = str(label or '').strip().lower()
        return text in {'1', '2', '3', '4', 'q1', 'q2', 'q3', 'q4', '1st', '2nd', '3rd', '4th'}

    @staticmethod
    def _label_is_first_half(label: str) -> bool:
        text = str(label or '').strip().lower()
        return text in {'1', '2', 'q1', 'q2', '1st', '2nd', 'h1', '1h', 'first half', 'first-half'}

    def get_period_snapshot_availability_report(self, *, max_snapshots: int = 250) -> dict[str, Any]:
        snapshot_dir = Path(self._snapshot_store._base_dir)  # noqa: SLF001
        files = sorted(snapshot_dir.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
        selected = files[: max(1, int(max_snapshots))]

        totals = {
            'snapshots_scanned': 0,
            'events_with_period_data': 0,
            'events_missing_period_data': 0,
            'events_with_complete_first_half': 0,
            'events_with_complete_quarters': 0,
            'events_with_missing_period_scoring': 0,
        }
        label_availability: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()

        for path in selected:
            totals['snapshots_scanned'] += 1
            try:
                snapshot = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue

            periods = snapshot.get('normalized_period_results') or []
            if not isinstance(periods, list) or not periods:
                totals['events_missing_period_data'] += 1
                continue

            totals['events_with_period_data'] += 1
            complete_by_label: dict[str, bool] = {}
            quarter_complete: dict[int, bool] = {1: False, 2: False, 3: False, 4: False}
            for item in periods:
                if not isinstance(item, dict):
                    continue
                label = str(item.get('period_label') or item.get('period_number') or '').strip()
                if not label:
                    continue
                label_availability[label] += 1
                is_complete = bool(item.get('is_score_complete'))
                complete_by_label[label] = is_complete
                source = str(item.get('source') or '').strip()
                if source:
                    source_counts[source] += 1

                number = item.get('period_number')
                if isinstance(number, int) and number in quarter_complete:
                    quarter_complete[number] = is_complete

            if any(not complete for complete in complete_by_label.values()):
                totals['events_with_missing_period_scoring'] += 1

            if quarter_complete[1] and quarter_complete[2]:
                totals['events_with_complete_first_half'] += 1
            if all(quarter_complete.values()):
                totals['events_with_complete_quarters'] += 1

        return {
            'totals': totals,
            'period_labels_available': dict(sorted(label_availability.items())),
            'period_extraction_sources': dict(sorted(source_counts.items())),
            'window': {
                'max_snapshots': max(1, int(max_snapshots)),
                'snapshot_dir': str(snapshot_dir),
            },
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


    def _readiness_status(self, *, runs: int, fallback_rate: float, missing_key_count: int, player_match_failures: int) -> str:
        if runs < self._readiness_min_samples:
            return 'partial'
        if fallback_rate >= self._readiness_not_ready_fallback_rate or missing_key_count > max(1, runs // 2):
            return 'not_ready'
        if fallback_rate <= self._readiness_ready_fallback_rate and player_match_failures <= max(1, runs // 10):
            return 'ready'
        return 'partial'

    def get_snapshot_market_coverage_report(self) -> dict[str, Any]:
        with self._lock:
            recent = [deepcopy(item) for item in self._grading_history]

        by_market: dict[str, dict[str, Any]] = defaultdict(lambda: {
            'runs': 0,
            'snapshot_successes': 0,
            'provider_fallbacks': 0,
            'missing_snapshot_keys': Counter(),
            'players_missing_stats': 0,
            'stat_family': None,
            'sports': set(),
            'leagues': set(),
            'event_ids': set(),
        })

        for run in recent:
            for detail in run.get('market_snapshot_details') or []:
                market_type = str(detail.get('market_type') or 'unknown').strip() or 'unknown'
                bucket = by_market[market_type]
                bucket['runs'] += 1
                if detail.get('used_snapshot'):
                    bucket['snapshot_successes'] += 1
                if detail.get('provider_fallback_used'):
                    bucket['provider_fallbacks'] += 1
                missing_key = detail.get('missing_snapshot_stat_key')
                if missing_key:
                    bucket['missing_snapshot_keys'][str(missing_key)] += 1
                if detail.get('player_id_resolved') and not detail.get('player_snapshot_found'):
                    bucket['players_missing_stats'] += 1
                if detail.get('stat_family') and not bucket['stat_family']:
                    bucket['stat_family'] = str(detail.get('stat_family'))
                if detail.get('sport'):
                    bucket['sports'].add(str(detail.get('sport')))
                if detail.get('league'):
                    bucket['leagues'].add(str(detail.get('league')))
                if detail.get('event_id'):
                    bucket['event_ids'].add(str(detail.get('event_id')))

        report: dict[str, Any] = {}
        for market_type in sorted(by_market):
            bucket = by_market[market_type]
            runs = int(bucket['runs'])
            fallbacks = int(bucket['provider_fallbacks'])
            fallback_rate = (fallbacks / runs) if runs else 0.0
            missing_keys = dict(sorted(bucket['missing_snapshot_keys'].items()))
            players_missing_stats = int(bucket['players_missing_stats'])
            status = self._readiness_status(
                runs=runs,
                fallback_rate=fallback_rate,
                missing_key_count=sum(missing_keys.values()),
                player_match_failures=players_missing_stats,
            )
            report[market_type] = {
                'runs': runs,
                'snapshot_successes': int(bucket['snapshot_successes']),
                'provider_fallbacks': fallbacks,
                'fallback_rate': round(fallback_rate, 4),
                'missing_snapshot_keys': missing_keys,
                'players_missing_stats': players_missing_stats,
                'stat_family': bucket['stat_family'],
                'sports': sorted(bucket['sports']),
                'leagues': sorted(bucket['leagues']),
                'event_ids': sorted(bucket['event_ids']),
                'status': status,
            }

        return {
            'markets': report,
            'thresholds': {
                'min_samples': self._readiness_min_samples,
                'ready_fallback_rate_max': self._readiness_ready_fallback_rate,
                'not_ready_fallback_rate_min': self._readiness_not_ready_fallback_rate,
            },
            'recent_grading_runs_count': len(recent),
        }

    def get_observability_snapshot(self) -> dict[str, Any]:
        with self._lock:
            grading = self._aggregate_grading_history()
            latest_hydration = deepcopy(self._latest_hydration_summary)
            hydration_history = [deepcopy(item) for item in self._hydration_history]

        market_readiness = self.get_snapshot_market_coverage_report()

        return {
            **grading,
            'market_readiness': market_readiness,
            'period_readiness': self.get_period_snapshot_availability_report(),
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
