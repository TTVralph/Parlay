# Sport Rule Coverage

This file summarizes stat-rule engine coverage by sport.

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
- player_points
- player_rebounds
- player_assists
- Future common markets: threes, PRA combos, team spreads/totals.

## MLB
- player_hits
- player_strikeouts
- player_total_bases (supports computed formula fallback)
- Future common markets: RBI, runs, hits+runs+rbi, pitcher outs.

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
