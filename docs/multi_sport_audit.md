# Multi-Sport Readiness Audit (ParlayBot)

## Architecture strengths
- Core parsing, normalization, grading, and resolver pipelines are modular and already passed around through services (`app/parser.py`, `app/services/*`, `app/resolver.py`).
- Provider abstractions already exist (`app/providers/base.py`, `app/services/provider_router.py`) so data-source routing is not tightly coupled to call-sites.
- Market metadata was already centralized in a single registry module, making extraction into sport registries low risk.

## Main blockers to clean multi-sport expansion
1. **NBA assumptions embedded in parsing and grading**
   - Basketball stat tokens (`PTS`, `REB`, `AST`, threes, first basket) are deeply embedded in parser and grader logic.
   - Play-by-play sequence settlement logic is basketball event-centric.
2. **Default-to-NBA behavior in multiple layers**
   - Model defaults, parser fallbacks, and UI text assume NBA unless explicitly overridden.
3. **Single shared dictionaries file mixed across sports**
   - Team/player/market aliases were aggregated into one module with no explicit per-sport boundary.
4. **Resolver flow has NBA-specific narrowing**
   - Scoreboard/date narrowing and team-resolution behavior include NBA checks in the main generic flow.

## Modules currently sport-specific
- `app/grader.py` (basketball stat maps, play-by-play event sequence assumptions)
- `app/providers/espn_provider.py` and `app/services/espn_plays_provider.py` (ESPN NBA endpoints/shape assumptions)
- `app/services/nba_game_resolver.py` and NBA player directory assets (`app/data/nba_players_directory.json`, `data/nba_players.json`, `data/nba_teams.json`)
- Front-end copy/sample payloads in `app/main.py` describing NBA as primary

## Modules already generic or mostly generic
- `app/providers/base.py` interfaces
- `app/services/provider_router.py`
- `app/services/slip_parser.py`, `app/services/slip_normalizer.py` (once fed sport-aware registries)
- `app/event_matcher.py` passthrough to resolver

## Refactor work completed in this change
1. Added sport-specific market registries in `app/markets/` with NBA implemented and MLB/NFL/WNBA registry slots.
2. Added sport-specific dictionary modules in `app/dictionaries/` and an aggregate API.
3. Added resolver hook dispatch point (`app/services/sport_resolver_hooks.py`) to keep generic resolver flow while enabling per-sport matching policies.
4. Added capability matrix (`app/sport_capabilities.py`) for feature gating by sport.
5. Kept existing NBA behavior as default path via compatibility wrappers (`app/services/market_registry.py`).

## Recommended implementation order
1. **WNBA next** (best fit): high parser/market/regrader similarity to NBA, minimal model drift.
2. MLB
3. NFL

Rationale: WNBA can reuse most NBA market semantics and resolver heuristics with mainly dictionary/provider identity deltas, while MLB/NFL need broader stat/event model and settlement-path adaptation.

## Suggested next milestones
- Move `app/grader.py` NBA stat constants into `app/settlement/nba.py` and add per-sport settlement strategy dispatch.
- Split ESPN provider logic by sport endpoint adapters.
- Introduce sport-aware parser token packs so regex sets are loaded from per-sport modules rather than a single blended pattern.
- Add capability-gated API responses so unsupported flows fail with explicit reason codes instead of silent fallbacks.
