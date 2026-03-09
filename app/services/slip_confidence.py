from __future__ import annotations

from .market_registry import MARKET_REGISTRY, normalize_market
from .slip_types import ParsedSlip


def apply_confidence_and_warnings(parsed: ParsedSlip, *, code_path: str = 'screenshot_parse') -> None:
    warnings = list(parsed.warnings)
    if not parsed.parsed_legs:
        parsed.confidence = 'low'
        warnings.append('empty parse -> fail')
        parsed.warnings = warnings
        return
    has_missing = False
    has_ambiguous = False
    seen: set[str] = set()
    for leg in parsed.parsed_legs:
        key = f'{leg.player_name}|{leg.market}|{leg.line}|{leg.selection}'.lower()
        if key in seen:
            warnings.append(f'duplicate legs -> warning: {leg.raw_text}')
        seen.add(key)
        if leg.market:
            raw_market = leg.market
            normalized_market = normalize_market(raw_market)
            registry_hit = bool(normalized_market and MARKET_REGISTRY.get(normalized_market))
            warnings.append(
                f"market debug -> path={code_path}; raw={raw_market}; normalized={normalized_market or 'none'}; registry_hit={'yes' if registry_hit else 'no'}"
            )
            if normalized_market:
                leg.market = normalized_market
            if not registry_hit:
                warnings.append(f'unsupported market -> warning: {raw_market}')
        if not leg.player_name or leg.line is None:
            has_missing = True
            warnings.append(f'missing player or line -> low confidence: {leg.raw_text}')
        if not leg.selection:
            has_ambiguous = True
            warnings.append(f'ambiguous parse -> NEEDS_REVIEW: {leg.raw_text}')
    if has_ambiguous:
        parsed.confidence = 'NEEDS_REVIEW'
    elif has_missing:
        parsed.confidence = 'low'
    elif warnings:
        parsed.confidence = 'medium'
    else:
        parsed.confidence = 'high'
    parsed.warnings = warnings


def should_fallback_to_ocr(parsed: ParsedSlip) -> bool:
    if not parsed.parsed_legs:
        return True
    if parsed.confidence in {'low', 'NEEDS_REVIEW'}:
        return True
    valid = [leg for leg in parsed.parsed_legs if leg.player_name and leg.line is not None and leg.selection]
    return len(valid) == 0
