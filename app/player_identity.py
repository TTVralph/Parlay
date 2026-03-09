from __future__ import annotations

from dataclasses import dataclass

from .identity_resolution import normalize_entity_name, resolve_player_identity as _resolve_identity


@dataclass(frozen=True)
class PlayerRecord:
    id: str
    canonical_name: str
    normalized_name: str
    team_id: str
    league: str
    espn_player_id: str
    sportsapipro_player_id: str | None = None


@dataclass(frozen=True)
class PlayerResolution:
    resolved_player_name: str
    resolved_player_id: str
    resolved_team: str | None
    resolution_confidence: float


def normalize_player_name(name: str) -> str:
    return normalize_entity_name(name)


def resolve_player_resolution(player_name: str | None, sport: str = 'NBA') -> PlayerResolution | None:
    result = _resolve_identity(player_name, sport=sport)
    if not result.resolved_player_id or not result.resolved_player_name:
        return None
    return PlayerResolution(
        resolved_player_name=result.resolved_player_name,
        resolved_player_id=result.resolved_player_id,
        resolved_team=result.resolved_team,
        resolution_confidence=result.confidence,
    )


def resolve_player_identity(player_name: str | None, sport: str = 'NBA') -> PlayerRecord | None:
    result = _resolve_identity(player_name, sport=sport)
    if not result.resolved_player_id or not result.resolved_player_name:
        return None
    return PlayerRecord(
        id=result.resolved_player_id,
        canonical_name=result.resolved_player_name,
        normalized_name=normalize_entity_name(result.resolved_player_name),
        team_id='',
        league=sport,
        espn_player_id='',
    )


def team_name_from_id(team_id: str | None) -> str | None:
    return None
