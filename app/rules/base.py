from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from app.services.event_snapshot import EventSnapshot


CompareFn = Callable[[float, float, str], str]
ComputeFn = Callable[[EventSnapshot, str | None, str | None], float | None]
KillConditionFn = Callable[[float, float, str, str | None], str | None]


def default_compare(actual_value: float, line: float, side: str) -> str:
    normalized_side = str(side or '').lower()
    if actual_value == line:
        return 'push'
    if normalized_side == 'over':
        return 'win' if actual_value > line else 'loss'
    if normalized_side == 'under':
        return 'win' if actual_value < line else 'loss'
    return 'unmatched'


def default_kill_condition(actual_value: float, line: float, side: str, event_status: str | None) -> str | None:
    normalized_side = str(side or '').lower()
    status = str(event_status or '').lower()
    if normalized_side == 'under' and actual_value > line:
        return 'threshold_exceeded'
    if normalized_side == 'over' and status == 'final' and actual_value <= line:
        return 'final_under'
    return None


@dataclass(frozen=True)
class StatRule:
    sport: str
    market_key: str
    stat_dependencies: tuple[str, ...]
    compute_actual_value: ComputeFn
    compare: CompareFn = default_compare
    kill_condition: KillConditionFn = default_kill_condition
    display_name: str | None = None
    supports_live_progress: bool = False
    supports_kill_moment: bool = False
    supports_team_markets: bool = False
    supports_player_markets: bool = True
    live_progress_components: tuple[str, ...] = field(default_factory=tuple)
    kill_moment_event_types: tuple[str, ...] = field(default_factory=tuple)

    def dependency_iter(self) -> Iterable[str]:
        return self.stat_dependencies
