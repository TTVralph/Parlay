from __future__ import annotations

import hashlib
from threading import Lock

from app.alias_runtime import get_alias_map
from app.models import Leg
from app.services.identity_normalizer import normalize_person_name
from app.services.slip_normalizer import normalize_market, normalize_selection

_SLIP_HASH_COUNTS: dict[str, int] = {}
_SLIP_HASH_LOCK = Lock()


def _normalize_player_name(player_name: str | None) -> str:
    raw_name = str(player_name or '').strip()
    if not raw_name:
        return 'unknown_player'

    player_aliases = get_alias_map('player')
    canonical = player_aliases.get(raw_name.lower(), raw_name)
    normalized = normalize_person_name(canonical)
    return normalized.replace(' ', '_') or 'unknown_player'


def _normalize_stat_type(leg: Leg) -> str:
    if leg.normalized_stat_type:
        return str(leg.normalized_stat_type).strip().lower().replace(' ', '_')

    normalized_market = normalize_market(leg.market_type)
    market = str(normalized_market or leg.market_type or '').strip().lower()
    if market.startswith('player_'):
        market = market[len('player_'):]
    return market.replace(' ', '_') or 'unknown_stat'


def _normalize_threshold(leg: Leg) -> str:
    threshold = leg.normalized_line_value if leg.normalized_line_value is not None else leg.line
    if threshold is None:
        return 'none'
    value = float(threshold)
    if value.is_integer():
        return str(int(value))
    return ('%f' % value).rstrip('0').rstrip('.')


def _fingerprint_leg(leg: Leg) -> str:
    player_name = leg.canonical_player_name or leg.resolved_player_name or leg.player
    direction = normalize_selection(leg.direction) or 'none'
    return '|'.join((
        _normalize_player_name(player_name),
        _normalize_stat_type(leg),
        direction,
        _normalize_threshold(leg),
    ))


def generate_slip_hash(legs: list[Leg]) -> str:
    normalized_legs = sorted(_fingerprint_leg(leg) for leg in legs)
    payload = ';'.join(normalized_legs)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def register_slip_hash(slip_hash: str) -> tuple[int, int, int]:
    with _SLIP_HASH_LOCK:
        previous = _SLIP_HASH_COUNTS.get(slip_hash, 0)
        _SLIP_HASH_COUNTS[slip_hash] = previous + 1
        duplicate_slip_count = sum(max(0, count - 1) for count in _SLIP_HASH_COUNTS.values())
        unique_slip_count = len(_SLIP_HASH_COUNTS)
        return _SLIP_HASH_COUNTS[slip_hash], duplicate_slip_count, unique_slip_count


def reset_slip_hash_index() -> None:
    with _SLIP_HASH_LOCK:
        _SLIP_HASH_COUNTS.clear()
