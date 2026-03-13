from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from app.models import Leg
from app.providers.base import EventInfo


@dataclass(frozen=True)
class SportResolverPolicy:
    candidate_ranker: Callable[[Leg, list[EventInfo], date | datetime | None], list[EventInfo]]
    team_filter_required: bool = True
    stat_availability_required: bool = False


ResolverHook = Callable[[Leg, list[EventInfo], date | datetime | None], list[EventInfo]]


def _default_ranker(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


def _nba_ranker(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    return candidates


def _mlb_ranker(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    if leg.market_type == 'player_hits':
        return candidates
    return candidates


def _nfl_ranker(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    if leg.market_type not in {'player_passing_yards', 'player_rushing_yards', 'player_receiving_yards'}:
        return candidates
    return candidates


def _hook_from_policy(policy: SportResolverPolicy) -> ResolverHook:
    def _hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
        return policy.candidate_ranker(leg, candidates, slip_value)

    return _hook


SPORT_RESOLVER_POLICIES: dict[str, SportResolverPolicy] = {
    'NBA': SportResolverPolicy(candidate_ranker=_nba_ranker, team_filter_required=True),
    'WNBA': SportResolverPolicy(candidate_ranker=_nba_ranker, team_filter_required=True),
    'MLB': SportResolverPolicy(candidate_ranker=_mlb_ranker, team_filter_required=True, stat_availability_required=True),
    'NFL': SportResolverPolicy(candidate_ranker=_nfl_ranker, team_filter_required=True, stat_availability_required=True),
}

SPORT_RESOLVER_HOOKS: dict[str, ResolverHook] = {
    sport: _hook_from_policy(policy)
    for sport, policy in SPORT_RESOLVER_POLICIES.items()
}


def get_sport_resolver_policy(sport: str | None) -> SportResolverPolicy:
    return SPORT_RESOLVER_POLICIES.get((sport or '').upper(), SportResolverPolicy(candidate_ranker=_default_ranker, team_filter_required=False))


def apply_sport_resolver_hook(leg: Leg, candidates: list[EventInfo], slip_value: date | datetime | None) -> list[EventInfo]:
    hook = SPORT_RESOLVER_HOOKS.get(leg.sport.upper(), _default_ranker)
    return hook(leg, candidates, slip_value)
