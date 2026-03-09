from __future__ import annotations

from .market_registry import normalize_market as normalize_market_with_registry


def normalize_market(market: str | None) -> str | None:
    if not market:
        return None
    normalized = normalize_market_with_registry(market)
    if normalized:
        return normalized
    return market.strip().lower()


def normalize_selection(selection: str | None) -> str | None:
    if not selection:
        return None
    s = selection.strip().lower()
    if s in {'o', 'over'}:
        return 'over'
    if s in {'u', 'under'}:
        return 'under'
    return s
