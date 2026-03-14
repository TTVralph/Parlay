# Sport Rule Coverage

This file summarizes stat-rule engine coverage by sport.

## Kill-moment definition

A **kill moment** is the first point where a leg becomes mathematically impossible to win.

- `under` legs are killed as soon as `actual_value > line` (`kill_reason = "threshold_exceeded"`).
- `over` legs are killed only when the event is final and `actual_value <= line` (`kill_reason = "final_under"`).
- If neither condition is true, `kill_moment` remains `false` and `kill_reason` remains `null`.

The rule engine evaluates this in each `StatRule` via `kill_condition(actual_value, line, bet_type, event_status)` and writes kill metadata to graded leg output.


## Graded leg progress metadata

Stat-rule graded legs now include `progress` metadata for ParlayBot live displays.

- Formula: `progress = actual_value / line`
- Output is clamped at a floor of `0.0` (negative ratios become `0.0`).
- Ratios above `1.0` are preserved to show overshooting the target.
- Value is rounded to 2 decimal places.
- Applies to combo stat markets too (for example `player_pra`, `player_pr`, `player_pa`, `player_ra`, and MLB `player_total_bases`).

Example:

```json
{
  "text": "Over 28.5 Points",
  "actual_value": 18,
  "line": 28.5,
  "progress": 0.63
}
```

## NBA
- player_points (live ✅, kill-moment ✅)
- player_rebounds (live ✅, kill-moment ✅)
- player_assists (live ✅, kill-moment ✅)
- player_threes
- player_pr (live ✅, kill-moment ✅)
- player_pa (live ✅, kill-moment ✅)
- player_ra (live ✅, kill-moment ✅)
- player_pra (live ✅, kill-moment ✅)
- moneyline (team-market scaffold)
- game_total (team-market scaffold)
- Future common markets: alternate lines, quarter/team derivatives, double-double/triple-double timelines.

## WNBA
- player_points (live ✅, kill-moment ✅)
- player_rebounds (live ✅, kill-moment ✅)
- player_assists (live ✅, kill-moment ✅)
- player_threes
- player_pr (live ✅, kill-moment ✅)
- player_pa (live ✅, kill-moment ✅)
- player_ra (live ✅, kill-moment ✅)
- player_pra (live ✅, kill-moment ✅)
- ESPN stat-key mapping includes WNBA-compatible aliases (e.g. `3PT` → `3PM`) for snapshot extraction parity.
- Future common markets: team spreads/totals.

## MLB
- player_hits (kill-moment ✅)
- player_strikeouts (kill-moment ✅)
- player_total_bases (kill-moment ✅, supports computed formula fallback: 1B + 2*2B + 3*3B + 4*HR)
- player_runs (kill-moment ✅)
- player_rbis (kill-moment ✅)
- player_home_runs (kill-moment ✅)
- Future common markets: hits+runs+rbi, pitcher outs.

## NFL
- player_passing_yards
- player_rushing_yards
- player_receiving_yards
- Future common markets: TDs, receptions, combo yards.

## NHL
- player_shots_on_goal
- player_points
- Future common markets: assists, blocked shots, saves.

## Soccer
- player_shots
- player_shots_on_target
- Future common markets: goals, assists, tackles, passes.

## UFC
- fight_winner (starter scaffold)
- Future common markets: method of victory, rounds, significant strikes.
