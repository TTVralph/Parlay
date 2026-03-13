from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from app.models import Leg
from app.providers.base import EventInfo

ResolverHook = Callable[[Leg, list[EventInfo], date | datetime | None], list[EventInfo]]


def _default_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


def _nba_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


def _mlb_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


def _nfl_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


SPORT_RESOLVER_HOOKS: dict[str, ResolverHook] = {
    'NBA': _nba_hook,
    'WNBA': _nba_hook,
    'MLB': _mlb_hook,
    'NFL': _nfl_hook,
}


def apply_sport_resolver_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    hook = SPORT_RESOLVER_HOOKS.get(leg.sport.upper(), _default_hook)
    return hook(leg, candidates, slip_value)
