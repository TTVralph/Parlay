# ParlayBot Check-Slip QA Pack

Use this pack after deploys for a quick reliability sanity pass across parser, frontend flow, and backend response shape.

## 1) Manual frontend regression checklist (/check)

1. Open `/check`.
2. Paste a text slip and click **Check Slip**.
   - Expected: no full-page refresh, results render in-place.
3. Upload an image screenshot and click **Check Slip**.
   - Expected: first click parses screenshot and populates textarea.
4. Click **Check Slip** again without changing screenshot.
   - Expected: request goes to grading path and returns leg results.
5. Upload screenshot, then click **Remove Screenshot**, then click **Check Slip**.
   - Expected: text grading path runs and returns results.
6. After grading, confirm these are enabled/visible:
   - Copy Summary
   - Copy Public Link (if public link returned)
   - Open Public Result (if public link returned)
   - Download Share Card
7. Validate payout area:
   - stake + odds → estimated payout/profit displayed
   - stake without odds → payout hint message displayed

## 2) Sample payloads for backend /check-slip

### Clean NBA slip
```
Jokic over 24.5 points
Denver ML
```

### Long slip (stress parser)
```
Denver ML leg 1
Denver ML leg 2
Denver ML leg 3
Denver ML leg 4
Denver ML leg 5
Denver ML leg 6
Denver ML leg 7
Denver ML leg 8
Denver ML leg 9
Denver ML leg 10
Denver ML leg 11
Denver ML leg 12
Denver ML leg 13
Denver ML leg 14
Denver ML leg 15
Denver ML leg 16
Denver ML leg 17
Denver ML leg 18
Denver ML leg 19
Denver ML leg 20
Denver ML leg 21
Denver ML leg 22
Denver ML leg 23
Denver ML leg 24
Denver ML leg 25
```

### Per-leg odds slip
```
Draymond Green Over 5.5 Assists +500
Quentin Grimes Over 22.5 Pts + Ast +250
```

### Stake without odds
```json
{"text": "Denver ML", "stake_amount": 20}
```

### Stake with odds
```json
{"text": "Denver ML\nOdds +150", "stake_amount": 20}
```

### Nonsense input
```
hello world
this is not a slip
foo bar baz
```

## 3) Fast local stress run

Run against a live local server:

```bash
python scripts/stress_check_slip.py --base-url http://127.0.0.1:8000 --runs 30 --concurrency 5
```

What to look for:
- No non-200 spikes.
- Stable average response time.
- `body.ok` distribution matches payload type (nonsense should be false; valid slips mostly true).

## 4) Persistence checks

- Submit the same valid slip multiple times.
- Confirm each successful response has a non-empty `public_id` and `public_url`.
- Open a few returned public URLs and confirm result page renders.
