# ParlayBot Maintainability/Safety Refactor Audit

Scope reviewed: parser/resolver/grader and adjacent helpers (`app/parser.py`, `app/resolver.py`, `app/grader.py`).

Goal: identify low-risk refactors that reduce bug risk without changing external behavior.

## Classification rubric
- **safe now**: mostly mechanical extraction/caching with minimal logic movement.
- **safe with tests first**: still low-risk, but touches core resolution/settlement paths where regression tests should gate changes.
- **risky / postpone**: complexity or behavior-coupled paths that should not be changed in a “safety-first” pass.

## Ranked top 10 safest refactors

1. **Extract a tiny parser helper for odds fields when creating `Leg` objects**  
   - **Classification:** safe now  
   - **Observed issue:** `american_odds=line_odds` and `decimal_odds=_american_to_decimal(...)` are repeated in almost every parse branch.  
   - **Why it reduces bug risk:** avoids branch drift where one branch forgets decimal odds conversion or handles `None` differently.  
   - **Tests needed before/after:** parser branch coverage (moneyline/spread/total/player prop) asserting identical odds fields.

2. **Extract and centralize “threes phrasing” normalization into one utility**  
   - **Classification:** safe now  
   - **Observed issue:** a long `.replace(...)` chain normalizes several “three pointers made” variants in-line.  
   - **Why it reduces bug risk:** one source of truth prevents missing a synonym in some parse paths and makes additions deterministic.  
   - **Tests needed before/after:** string normalization unit tests for each phrase variant currently present.

3. **Request-scope cache alias maps and player resolution inside `parse_text`**  
   - **Classification:** safe now  
   - **Observed issue:** `_team_lookup`, `_player_lookup`, `_market_lookup` repeatedly call alias/map resolution for each leg.  
   - **Why it reduces bug risk:** fewer repeated lookups lowers surface for inconsistent map snapshots and reduces latency spikes on long slips.  
   - **Tests needed before/after:** long multi-leg parse test confirming identical parsed payload and confidences.

4. **Consolidate provider “optional signature” fallback wrappers in resolver**  
   - **Classification:** safe now  
   - **Observed issue:** `_team_candidates`, `_player_candidates`, and `_player_team_for_date` repeat `try/except TypeError` compatibility logic.  
   - **Why it reduces bug risk:** prevents future mismatch where one wrapper handles legacy provider signatures differently from others.  
   - **Tests needed before/after:** provider compatibility tests (legacy/no `include_historical` arg vs modern signature).

5. **Deduplicate event-date quality recomputation per candidate list**  
   - **Classification:** safe now  
   - **Observed issue:** `_event_date_match_quality(...)` is repeatedly recomputed over the same candidate lists during ranking/filtering/selection.  
   - **Why it reduces bug risk:** single computed quality map reduces inconsistent “exact/nearby/mismatch” outcomes from accidental diverging calls and simplifies reasoning.  
   - **Tests needed before/after:** resolver tests asserting same chosen event and same `event_date_match_quality` metadata.

6. **Introduce a parser helper for default unresolved/unmatched leg construction**  
   - **Classification:** safe now  
   - **Observed issue:** fallback/default values (notes/confidence/sport defaults) are inlined in multiple parse branches.  
   - **Why it reduces bug risk:** keeps unresolved-leg semantics consistent, especially when new markets are added.  
   - **Tests needed before/after:** unmatched parse regression tests asserting notes/confidence unchanged.

7. **Prove and remove dead private helper `_snapshot_player_entry` in grader**  
   - **Classification:** safe now (after usage proof)  
   - **Observed issue:** private helper is defined but not referenced in runtime code paths.  
   - **Why it reduces bug risk:** less dead code means fewer stale alternatives that can be mistakenly revived or edited inconsistently.  
   - **Tests needed before/after:** static reference check + full grader test subset (`settle_leg`, `grade_text`) to confirm no impact.

8. **Extract candidate filtering pipeline in resolver into a single ordered helper**  
   - **Classification:** safe with tests first  
   - **Observed issue:** sequence of matchup/opponent/date/team filters and warnings is dense and stateful.  
   - **Why it reduces bug risk:** explicit pipeline order reduces accidental reorder bugs and makes warning emission consistent.  
   - **Tests needed before/after:** identity drift + ambiguous event tests + mismatch warning tests with snapshot assertions on warning arrays.

9. **Extract guardrail-review leg update builder from resolver**  
   - **Classification:** safe with tests first  
   - **Observed issue:** `_review_due_to_guardrail` mutates a broad update payload with many coupled fields.  
   - **Why it reduces bug risk:** concentrated builder logic makes it harder to forget one required review field when adding new guardrails.  
   - **Tests needed before/after:** tests asserting all review-mode fields are populated (`status`, `method`, reason codes, warnings, confidence).

10. **Move repeated event-sequence selector branches in grader to a table-driven map**  
   - **Classification:** safe with tests first  
   - **Observed issue:** `_select_event_sequence_winner` has many very similar branch blocks for first/last events.  
   - **Why it reduces bug risk:** table-driven extraction avoids copy/paste predicate mistakes (wrong player field or event flag).  
   - **Tests needed before/after:** per-market sequence tests (first basket/three/rebound/assist/steal/block + last basket).

## Risky / postpone items (not in top-10 “safest now” plan)

- **Large decomposition of `resolve_leg_events` (1144-line module with a very large orchestration function)**  
  - **Classification:** risky / postpone  
  - **Reason:** behavior is tightly coupled to notes/warnings/cache side effects; broad extraction could alter review routing.

- **Large decomposition of `grade_text`/settlement flow in `grader.py` (1772-line module)**  
  - **Classification:** risky / postpone  
  - **Reason:** settlement payload/reason-code compatibility is externally visible; refactor should follow stronger golden tests.

## Minimum test guardrails before touching core resolver/grader

- Golden snapshot tests for response payload shape and key metadata fields.
- Deterministic regression suite for ambiguous-player, multi-candidate-event, and mismatch-review scenarios.
- Market coverage tests for event-sequence and milestone props.
