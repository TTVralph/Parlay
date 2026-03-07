# ParlayBot Step 14

New in step 14:
- subscription plans and mock checkout flow
- user subscription endpoints: `/billing/plans`, `/billing/subscribe`, `/billing/me`
- affiliate link plumbing: `/affiliate/links`, `/affiliate/resolve`
- capper verification badges with admin verification endpoints
- public capper profiles now expose verification state
- added step 14 tests for billing, affiliate links, and verification

# ParlayBot Step 13

New in step 13:
- real migration tracking via `schema_migrations`
- role-based auth for `member`, `capper`, and `admin` users
- capper self-service endpoints: `GET /capper/me`, `PATCH /capper/me`
- admin role management endpoint: `POST /admin/users/{user_id}/role`
- deploy-ready static frontend build served from `/app` with bundled assets under `/assets/*`

# Parlay Bot - Step 12

This build adds:
- real user auth (`/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`)
- persistent admin sessions (`/admin/auth/login`, `/admin/auth/sessions`)
- a React dashboard page at `/app`
- DB tables for `users` and `user_sessions`

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/app` for the dashboard.

The legacy public pages still exist:
- `/leaderboard`
- `/cappers/{username}`

Admin options:
- static bearer token via `ADMIN_API_TOKEN`
- persistent admin login via `POST /admin/auth/login`

# Parlay Cash Checker MVP

## Step 8 upgrade included here
This version adds the first analyst-facing tooling layer on top of the grading backend:
- manual leg-edit regrading for review tickets
- ticket financials for stake, odds, bookmaker, and computed profit
- ROI dashboards by capper
- bookmaker slip templates for cleaner manual entry and OCR cleanup

## What step 8 adds
- `GET /slips/templates`
- `POST /tickets/{ticket_id}/financials`
- `POST /tickets/{ticket_id}/manual-regrade`
- `GET /dashboard/cappers-roi`
- `GET /dashboard/cappers-roi/{username}`

## Existing core features still included
- parse and grade pasted parlays
- event/date resolution from `posted_at`
- tweet/X ingestion and screenshot OCR ingestion
- review queue
- watched X accounts and polling runs
- alias admin tools
- dedupe and scheduled polling
- capper hit-rate dashboard

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Ticket financials example
```bash
curl -X POST http://127.0.0.1:8000/tickets/<ticket_id>/financials \
  -H "Content-Type: application/json" \
  -d '{"stake_amount":25,"american_odds":200,"bookmaker":"draftkings"}'
```

## Manual regrade example
```bash
curl -X POST http://127.0.0.1:8000/tickets/<ticket_id>/manual-regrade \
  -H "Content-Type: application/json" \
  -d '{
    "legs":[
      {"leg_index":1,"player":"Nikola Jokic","market_type":"player_points","direction":"over","line":24.5,"confidence":0.95}
    ],
    "resolve_review_id":1,
    "resolution_note":"Resolved alias manually"
  }'
```

## Slip template example
```bash
curl http://127.0.0.1:8000/slips/templates
```

## ROI dashboard example
```bash
curl http://127.0.0.1:8000/dashboard/cappers-roi
curl http://127.0.0.1:8000/dashboard/cappers-roi/roi-capper
```

## Providers
### X provider
```bash
export X_PROVIDER=mock
```
Optional real API mode:
```bash
export X_PROVIDER=api_v2
export X_BEARER_TOKEN=your_token_here
```

### OCR provider
```bash
export OCR_PROVIDER=mock
```
Optional production-shaped modes:
```bash
export OCR_PROVIDER=tesseract
# or
export OCR_PROVIDER=ocr_space
export OCR_SPACE_API_KEY=your_key_here
```

### Results provider
```bash
export RESULTS_PROVIDER=sample
```
Optional JSON snapshots:
```bash
export RESULTS_PROVIDER=json
export RESULTS_EVENTS_PATH=/absolute/path/events.json
export RESULTS_PLAYER_RESULTS_PATH=/absolute/path/player_results.json
```

## Test status
- 17 tests passing

## Recommended step 9
- exact odds extraction from bookmaker OCR text
- decimal odds support and payout normalization
- multi-sport expansion beyond NBA
- admin UI for review queue and capper dashboards
- webhook/push notifications when watched tickets settle


## Step 16 additions

- optional Stripe SDK gateway scaffold via `STRIPE_USE_SDK=true` and `STRIPE_SECRET_KEY`
- subscription lifecycle endpoints:
  - `POST /billing/cancel`
  - `POST /billing/resume`
  - `POST /billing/portal`
  - `GET /billing/account`
- richer account UI at `/app` and `/account`
- provider customer/subscription IDs persisted on subscriptions


## Step 17 additions

- Email notification log for billing lifecycle events
- Billing invoices/history endpoints
- Affiliate conversion tracking and analytics

### New endpoints

- `GET /billing/history`
- `GET /billing/invoices`
- `GET /billing/emails`
- `POST /affiliate/conversions`
- `GET /affiliate/conversions`

### Stripe event side effects

The webhook flow now:
- stores paid invoices
- creates email notification records for activation, payment success, payment failure, and cancellation
- enriches billing history views


## Step 18 additions
- real outbound email provider scaffolding via `EMAIL_PROVIDER=mock|smtp`
- invoice PDF links and authenticated/tokenized PDF downloads
- affiliate postback + webhook ingestion endpoints and event log
