from __future__ import annotations

from dataclasses import dataclass

_SUPPORTED_STRATEGIES = {'bet365', 'fanduel', 'draftkings', 'prizepicks_like', 'unknown'}

_SHARED_SYSTEM_RULES = """You are a sportsbook slip parser.

Extract complete player prop bet legs from the screenshot.

Rules:
- Return structured JSON only.
- Normalize markets into these exact names only:
  points, rebounds, assists, threes, steals, blocks, pra, pr, pa, ra
- Normalize selections into:
  over, under
- Preserve player_name exactly as shown in the screenshot.
- Preserve a short raw_text for each leg.
- Legs may be visually multi-line. You may associate adjacent lines in the same row/card (e.g. player name line, market subtitle line, and selection/line) when layout strongly indicates they belong together.
- Do not require all useful text for a leg to be present in a single line string.
- If likely player prop rows are present but line/market association is unclear, omit uncertain legs and add warnings like:
  - Detected likely player prop rows but line/market association was unclear
  - Image may contain multi-line leg layout
- Extract only complete, high-confidence legs.
- If a leg is incomplete or unclear, omit it and add a warning.
- If the screenshot shows LIVE, a quarter/period marker, a game clock, or in-progress indicators, set screenshot_state to \"live\".
- If unclear, set screenshot_state to \"unknown\".
- Do not guess missing values.
"""

_SHARED_USER_PROMPT = (
    'Extract sportsbook player prop bet legs from this screenshot. '
    'Return only the structured output matching the schema.'
)


@dataclass(frozen=True)
class VisionPromptStrategy:
    system_prompt: str
    user_prompt: str
    layout_notes: str
    parser_strategy_used: str


_LAYOUT_NOTES = {
    'bet365': """Strategy: bet365 layout.
- Ignore UI elements: bet slip title bars, same game parlay promos, cashout widgets, green accents, and odds chips not attached to player rows.
- Expected leg row structure: one row/card per leg with player name first, then market subtitle, then selection with line.
- Player name usually shown as a standalone top line in each row.
- Market subtitle usually shown directly beneath the player name (e.g., Points, Assists, Rebounds).
- Line/selection usually shown as Over/Under with a decimal line on the same or adjacent line.
- Ignore live score/clock/header elements even when they appear near the top of the screenshot.""",
    'fanduel': """Strategy: fanduel layout.
- Ignore UI elements: navigation tabs, boosted odds banners, edit-bet controls, payout summaries, and tokenized market pills.
- Expected leg row structure: stacked cards where player name and market label appear together, with selection/line nearby in the same card.
- Player name is usually shown in larger text at the start of the card.
- Market subtitle is usually shown as a compact stat label under or next to the player name.
- Line/selection is usually shown as Over/Under and numeric line in bold treatment.
- Ignore live score ribbons, period/clock, and persistent app headers.""",
    'draftkings': """Strategy: draftkings layout.
- Ignore UI elements: DK app chrome, SGP badges, odds changes arrows, bet slip footer totals, and promotional banners.
- Expected leg row structure: multi-line row with player name line, stat market line, and explicit Over/Under line.
- Player name is usually isolated on the first line of each leg row.
- Market subtitle is usually shown on the next line and may include shorthand stat naming.
- Line/selection is usually shown as Over/Under with decimal line, sometimes wrapped to adjacent line.
- Ignore scoreboards, game clock, and matchup headers when extracting legs.""",
    'prizepicks_like': """Strategy: prizepicks_like layout.
- Ignore UI elements: flex/power mode toggles, multiplier banners, entry summary widgets, and payout sliders.
- Expected leg row structure: tile/card per pick with player name and stat line merged across one or two lines.
- Player name is usually shown prominently at the top of each tile.
- Market subtitle is usually shown as stat + opponent/context text directly under name.
- Line/selection is usually implied via More/Less (map to over/under) with a numeric line.
- Ignore live score headers, countdown clocks, and sticky navigation bars.""",
    'unknown': """Strategy: unknown generic sportsbook layout.
- Ignore UI elements: app headers, nav tabs, payout/odds summaries, promos, and controls not part of leg rows.
- Expected leg row structure: likely multi-line clusters where player name, market subtitle, and selection/line appear together.
- Player name is usually title-cased and adjacent to the market information.
- Market subtitle is usually a stat descriptor close to the player name.
- Line/selection is usually Over/Under (or synonyms) paired with a numeric line.
- Ignore scoreboards, game clocks, and live/in-progress banners when identifying legs.""",
}


def build_vision_prompts(detected_sportsbook: str) -> VisionPromptStrategy:
    strategy = detected_sportsbook if detected_sportsbook in _SUPPORTED_STRATEGIES else 'unknown'
    layout_notes = _LAYOUT_NOTES[strategy]
    system_prompt = f"{_SHARED_SYSTEM_RULES}\n\nLayout-specific notes:\n{layout_notes}"
    user_prompt = f"Detected sportsbook layout hint: {detected_sportsbook}.\nParser strategy: {strategy}.\n{_SHARED_USER_PROMPT}"
    return VisionPromptStrategy(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        layout_notes=layout_notes,
        parser_strategy_used=strategy,
    )
