from __future__ import annotations

from collections import defaultdict
from sqlalchemy.orm import Session

from .db.models import AliasOverrideORM
from .dictionaries import MARKET_ALIASES, PLAYER_ALIASES, TEAM_ALIASES

_RUNTIME: dict[str, dict[str, str]] = {
    'player': dict(PLAYER_ALIASES),
    'team': dict(TEAM_ALIASES),
    'market': dict(MARKET_ALIASES),
}


def get_alias_map(alias_type: str) -> dict[str, str]:
    return _RUNTIME[alias_type]



def reset_runtime_aliases() -> None:
    _RUNTIME['player'] = dict(PLAYER_ALIASES)
    _RUNTIME['team'] = dict(TEAM_ALIASES)
    _RUNTIME['market'] = dict(MARKET_ALIASES)



def load_alias_overrides(db: Session) -> dict[str, int]:
    reset_runtime_aliases()
    counts: dict[str, int] = defaultdict(int)
    rows = list(db.query(AliasOverrideORM).all())
    for row in rows:
        alias_type = row.alias_type.lower().strip()
        if alias_type not in _RUNTIME:
            continue
        _RUNTIME[alias_type][row.alias.lower().strip()] = row.canonical_value
        counts[alias_type] += 1
    return dict(counts)
