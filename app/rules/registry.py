from __future__ import annotations

from app.rules.base import StatRule
from app.rules.mlb import MLB_RULES
from app.rules.nba import NBA_RULES
from app.rules.nfl import NFL_RULES
from app.rules.nhl import NHL_RULES
from app.rules.soccer import SOCCER_RULES
from app.rules.ufc import UFC_RULES
from app.rules.wnba import WNBA_RULES

_RULES: dict[str, dict[str, StatRule]] = {
    'NBA': NBA_RULES,
    'WNBA': WNBA_RULES,
    'MLB': MLB_RULES,
    'NFL': NFL_RULES,
    'NHL': NHL_RULES,
    'SOCCER': SOCCER_RULES,
    'UFC': UFC_RULES,
}


def get_sport_rules(sport: str | None) -> dict[str, StatRule]:
    if not sport:
        return {}
    return _RULES.get(str(sport).upper(), {})


def get_stat_rule(sport: str | None, market_key: str) -> StatRule | None:
    return get_sport_rules(sport).get(market_key)


def has_stat_rule(sport: str | None, market_key: str) -> bool:
    return get_stat_rule(sport, market_key) is not None


def list_rule_coverage() -> dict[str, list[StatRule]]:
    return {sport: list(rules.values()) for sport, rules in _RULES.items()}
