from __future__ import annotations

from . import mlb, nba, nfl, wnba

SPORT_DICTIONARIES = {
    'NBA': nba,
    'MLB': mlb,
    'NFL': nfl,
    'WNBA': wnba,
}


def _merge(attr: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for module in SPORT_DICTIONARIES.values():
        merged.update(getattr(module, attr))
    return merged


def get_sport_dictionary(sport: str | None) -> object | None:
    return SPORT_DICTIONARIES.get((sport or '').upper())


def get_team_aliases(sport: str | None = None) -> dict[str, str]:
    module = get_sport_dictionary(sport)
    if module:
        return dict(getattr(module, 'TEAM_ALIASES'))
    return _merge('TEAM_ALIASES')


def get_player_aliases(sport: str | None = None) -> dict[str, str]:
    module = get_sport_dictionary(sport)
    if module:
        return dict(getattr(module, 'PLAYER_ALIASES'))
    return _merge('PLAYER_ALIASES')


def get_market_aliases(sport: str | None = None) -> dict[str, str]:
    module = get_sport_dictionary(sport)
    if module:
        return dict(getattr(module, 'MARKET_ALIASES'))
    return _merge('MARKET_ALIASES')


TEAM_ALIASES = _merge('TEAM_ALIASES')
PLAYER_ALIASES = _merge('PLAYER_ALIASES')
MARKET_ALIASES = _merge('MARKET_ALIASES')
TEAM_SPORTS = _merge('TEAM_SPORTS')
PLAYER_SPORTS = _merge('PLAYER_SPORTS')


def get_team_context_lookup(sport: str | None = None) -> dict[str, str]:
    aliases = get_team_aliases(sport)
    return {str(alias).lower(): team for alias, team in aliases.items()}


def get_player_context_lookup(sport: str | None = None) -> dict[str, str]:
    aliases = get_player_aliases(sport)
    return {str(alias).lower(): player for alias, player in aliases.items()}
