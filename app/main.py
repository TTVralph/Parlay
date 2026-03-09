from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import os
import threading
import time
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .alias_runtime import load_alias_overrides
from .auth import bearer, create_session_token, get_user_session, hash_password, require_admin, require_capper_session, require_user_session, session_expiry, verify_password
from .alias_store import list_aliases, upsert_alias
from .bookmaker_parsers import parse_slip_text
from .financials import extract_financials
from .db import models as _db_models  # noqa: F401
from .db.base import Base
from .db.session import SessionLocal, engine, get_db, run_lightweight_migrations
from .grader import grade_text, settle_leg
from .ingestion import dump_source_payload, normalize_tweet_payload
from .models import (
    OddsMatchRequest,
    OddsMatchResponse,
    PublicCapperProfileResponse,
    PublicLeaderboardResponse,
    PublicLeaderboardRow,
    ModerationRequest,
    CapperModerationResponse,
    AdminAuthStatusResponse,
    CapperRoiDashboardResponse,
    CapperRoiDashboardRow,
    AliasResponse,
    AliasUpsertRequest,
    GradeRequest,
    GradeResponse,
    CheckJobCreateResponse,
    CheckJobStatusResponse,
    IngestGradeResponse,
    OCRExtractResponse,
    ParseRequest,
    ParseResponse,
    PollAccountRequest,
    PollRunResponse,
    SchedulerRunResponse,
    SchedulerStatusResponse,
    ReviewQueueItemResponse,
    ReviewResolveRequest,
    ManualTicketRegradeRequest,
    TicketFinancialsUpdateRequest,
    SlipTemplateResponse,
    SlipParseRequest,
    SlipParseResponse,
    TicketDeduplicationResponse,
    TicketDetailResponse,
    TweetIngestRequest,
    WatchAccountRequest,
    WatchAccountResponse,
    XFetchRequest,
    CapperDashboardResponse,
    CapperDashboardRow,
    UserRegisterRequest,
    UserLoginRequest,
    AdminLoginRequest,
    UserProfileResponse,
    SessionResponse,
    LogoutResponse,
    AdminSessionRow,
    AdminSessionsResponse,
    UserRoleUpdateRequest,
    CapperSelfProfileResponse,
    CapperSelfProfileUpdateRequest,
    AdminCapperCreateRequest,
    AdminCapperUpdateRequest,
    AdminCapperProfileResponse,
    SubscriptionPlanResponse,
    SubscriptionPlansResponse,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    UserSubscriptionResponse,
    BillingEntitlementsResponse,
    BillingAccountResponse,
    BillingEventRow,
    SubscriptionCancelRequest,
    BillingPortalRequest,
    BillingPortalResponse,
    BillingInvoicesResponse,
    BillingInvoiceRow,
    BillingInvoiceLinksResponse,
    SignedInvoiceLinkResponse,
    BillingHistoryResponse,
    EmailNotificationRow,
    EmailNotificationsResponse,
    AffiliateConversionRecordRequest,
    AffiliatePostbackRequest,
    AffiliateWebhookIngestRequest,
    AffiliateWebhookEventRow,
    AffiliateWebhookEventsResponse,
    AffiliateConversionRow,
    AffiliateConversionsResponse,
    StripeCheckoutRequest,
    StripeWebhookEventRequest,
    StripeWebhookResponse,
    AffiliateLinkUpsertRequest,
    AffiliateLinkResponse,
    AffiliateResolveRequest,
    AffiliateResolveResponse,
    AffiliateAnalyticsRow,
    AffiliateAnalyticsResponse,
    CapperVerificationRequest,
    CapperVerificationResponse,
    AllSportsGamesResponse,
    AllSportsStatsResponse,
    SportsAPIProGamesResponse,
    SportsAPIProAthleteGameLogsResponse,
    ProviderCapabilitiesResponse,
    SportsAPIProAthleteGamesResponse,
)
from .ocr import get_ocr_provider
from .ocr.providers import validate_image_upload
from .parser import parse_text
from .screenshot_parser import parse_screenshot_text
from .odds_matcher import match_ticket_odds
from .providers.allsports_client import AllSportsClient, AllSportsError
from .providers.allsports_normalizer import (
    ALLSPORTS_PROVIDER_CAPABILITIES,
    StatsPayloadShapeError,
    normalize_games,
    normalize_match_stats,
    safe_payload_preview,
    summarize_stats_payload_shape,
)
from .providers.sportsapipro_client import SportsAPIProClient, SportsAPIProError
from .providers.sportsapipro_normalizer import (
    SPORTSAPIPRO_PROVIDER_CAPABILITIES,
    SportsAPIProNormalizeError,
    normalize_athlete_game_logs,
    normalize_games as normalize_sportsapipro_games,
)
from .providers.espn_provider import ESPNNBAResultsProvider
from .providers.sportsapipro_client import SportsAPIProClient, SportsAPIProError
from .providers.sportsapipro_normalizer import (
    SPORTSAPIPRO_PROVIDER_CAPABILITIES,
    normalize_athlete_games_payload,
    normalize_games_payload,
)
from .polling import poll_account_once
from .scheduler import get_scheduler_config, run_due_polls_once, start_scheduler_thread
from .services.repository import (
    enqueue_review_if_needed,
    get_ticket,
    list_poll_runs,
    list_review_items,
    list_watched_accounts,
    compute_capper_dashboard,
    compute_capper_roi_dashboard,
    find_duplicate_ticket,
    resolve_review_item,
    save_graded_ticket,
    update_ticket_financials,
    manual_regrade_ticket,
    upsert_watched_account,
    get_or_create_capper_profile,
    list_capper_profiles,
    get_capper_profile,
    create_capper_profile,
    update_capper_profile_admin,
    set_capper_profile_visibility,
    hide_ticket,
    unhide_ticket,
    list_hidden_tickets,
    create_user,
    create_user_session,
    get_user_by_username,
    revoke_user_session,
    list_admin_sessions,
    set_user_role,
    claim_capper_profile,
    update_capper_profile_self,
    seed_subscription_plans,
    list_subscription_plans,
    create_subscription_checkout,
    create_stripe_checkout,
    activate_subscription_checkout,
    apply_stripe_event,
    get_active_subscription,
    cancel_user_subscription,
    resume_user_subscription,
    create_billing_portal_link,
    get_billing_account_summary,
    get_billing_history,
    list_billing_invoices,
    get_billing_invoice_for_user,
    build_invoice_download_url,
    build_signed_invoice_url,
    verify_signed_invoice_access,
    render_invoice_pdf,
    list_email_notifications,
    get_user_entitlements,
    user_has_entitlement,
    list_affiliate_links,
    affiliate_analytics,
    record_affiliate_conversion,
    list_affiliate_conversions,
    ingest_affiliate_postback,
    list_affiliate_webhook_events,
    upsert_affiliate_link,
    resolve_affiliate_url,
    set_capper_verification,
)
from .providers.factory import get_results_provider
from .services.serializers import (
    alias_to_response,
    poll_run_to_response,
    review_item_to_response,
    ticket_to_response,
    watched_account_to_response,
)
from .x_client import get_x_client

app = FastAPI(title='Parlay Cash Checker MVP', version='1.9.0')
logger = logging.getLogger(__name__)
run_lightweight_migrations()


_public_check_rate_limit_lock = threading.Lock()
_public_check_rate_limit_hits: dict[str, list[float]] = {}
_public_check_jobs_lock = threading.Lock()
_public_check_jobs: dict[str, dict] = {}
_public_check_provider = ESPNNBAResultsProvider()


def _cleanup_public_check_jobs() -> None:
    ttl_seconds = int(os.getenv('PUBLIC_CHECK_JOB_TTL_SECONDS', '900'))
    max_jobs = int(os.getenv('PUBLIC_CHECK_JOB_MAX_STORED', '1000'))
    now = time.time()
    expired = []
    for job_id, item in _public_check_jobs.items():
        if item.get('status') == 'pending':
            continue
        completed_at = item.get('completed_at', now)
        if now - completed_at > ttl_seconds:
            expired.append(job_id)
    for job_id in expired:
        _public_check_jobs.pop(job_id, None)
    if len(_public_check_jobs) > max_jobs:
        ordered = sorted(_public_check_jobs.items(), key=lambda kv: kv[1].get('submitted_at', 0.0))
        for job_id, _row in ordered[: max(0, len(_public_check_jobs) - max_jobs)]:
            _public_check_jobs.pop(job_id, None)


def _extract_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get('x-forwarded-for')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip() or 'unknown'
    if request.client and request.client.host:
        return request.client.host
    return 'unknown'


def _enforce_public_check_rate_limit(request: Request, response: Response, route_tag: str) -> None:
    limit_per_min = int(os.getenv('PUBLIC_CHECK_RATE_LIMIT_PER_MINUTE', '60'))
    if limit_per_min <= 0:
        return
    window_seconds = int(os.getenv('PUBLIC_CHECK_RATE_LIMIT_WINDOW_SECONDS', '60'))
    now = time.time()
    cutoff = now - window_seconds
    key = f'{route_tag}:{_extract_client_ip(request)}'

    with _public_check_rate_limit_lock:
        hits = [ts for ts in _public_check_rate_limit_hits.get(key, []) if ts >= cutoff]
        if len(hits) >= limit_per_min:
            retry_after = max(1, int(hits[0] + window_seconds - now))
            response.headers['Retry-After'] = str(retry_after)
            raise HTTPException(status_code=429, detail='Too many slip checks. Please try again shortly.')
        hits.append(now)
        _public_check_rate_limit_hits[key] = hits

FRONTEND_DIST = Path(__file__).resolve().parent / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIST / 'assets'), name='assets')


def _user_to_response(user: _db_models.UserORM) -> UserProfileResponse:
    return UserProfileResponse(id=user.id, username=user.username, email=user.email, is_admin=user.is_admin, role=(user.role or ('admin' if user.is_admin else 'member')), linked_capper_username=user.linked_capper_username, created_at=user.created_at)


def _session_to_response(session: _db_models.UserSessionORM) -> SessionResponse:
    return SessionResponse(access_token=session.session_token, expires_at=session.expires_at, user=_user_to_response(session.user))


def _capper_admin_profile_to_response(row: _db_models.CapperProfileORM) -> AdminCapperProfileResponse:
    return AdminCapperProfileResponse(
        username=row.username,
        is_public=row.is_public,
        moderation_note=row.moderation_note,
        display_name=row.display_name,
        bio=row.bio,
        verified=row.is_verified,
        verification_badge=row.verification_badge,
    )


def _billing_to_response(sub: _db_models.UserSubscriptionORM) -> UserSubscriptionResponse:
    return UserSubscriptionResponse(subscription_id=sub.id, plan_code=sub.plan_code, status=sub.status, provider=sub.provider, provider_customer_id=sub.provider_customer_id, provider_subscription_id=sub.provider_subscription_id, started_at=sub.started_at, current_period_end=sub.current_period_end, cancel_at_period_end=sub.cancel_at_period_end)


def require_entitlement(entitlement: str):
    def _dependency(credentials = Depends(bearer), db: Session = Depends(get_db)) -> _db_models.UserSessionORM:
        session = get_user_session(credentials, db)
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User auth required')
        if session.user.is_admin or user_has_entitlement(db, session.user, entitlement):
            return session
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'{entitlement} entitlement required')
    return _dependency


def verify_stripe_signature(raw_body: bytes, signature: str | None) -> bool:
    import hashlib
    import hmac
    import json
    import os

    secret = os.getenv('STRIPE_WEBHOOK_SECRET', 'dev-stripe-webhook-secret')
    if not signature:
        return False
    provided = signature.strip()
    candidates = [hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()]
    try:
        canonical = json.dumps(json.loads(raw_body.decode('utf-8')), sort_keys=True, separators=(',', ':')).encode('utf-8')
        candidates.append(hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).hexdigest())
        relaxed = json.dumps(json.loads(raw_body.decode('utf-8'))).encode('utf-8')
        candidates.append(hmac.new(secret.encode('utf-8'), relaxed, hashlib.sha256).hexdigest())
    except Exception:
        pass
    return any(hmac.compare_digest(candidate, provided) for candidate in candidates)


@app.on_event('startup')
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    db = SessionLocal()
    try:
        load_alias_overrides(db)
        seed_subscription_plans(db)
    finally:
        db.close()
    start_scheduler_thread()


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}




def _parse_iso_date(raw_date: str) -> date:
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid date format. Use YYYY-MM-DD') from exc


def _build_allsports_client() -> AllSportsClient:
    try:
        return AllSportsClient.from_env()
    except AllSportsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _build_sportsapipro_client() -> SportsAPIProClient:
    try:
        return SportsAPIProClient.from_env()
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.get('/api/allsports/games', response_model=AllSportsGamesResponse)
def allsports_games(date: str) -> AllSportsGamesResponse:
    parsed_date = _parse_iso_date(date)
    client = _build_allsports_client()
    logger.info('AllSports games lookup date=%s', date)
    try:
        events = client.get_games_by_date(parsed_date)
    except AllSportsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    games = normalize_games(events)
    return AllSportsGamesResponse(date=date, games=games)


@app.get('/api/allsports/match/{match_id}/stats', response_model=AllSportsStatsResponse)
def allsports_match_stats(match_id: str) -> AllSportsStatsResponse:
    if not match_id.strip():
        raise HTTPException(status_code=400, detail='match_id is required')
    client = _build_allsports_client()
    logger.info('AllSports stats lookup match_id=%s', match_id)
    try:
        payload = client.get_match_statistics(match_id)
        logger.info(
            'AllSports stats upstream payload match_id=%s top_level_type=%s top_level_keys=%s',
            match_id,
            type(payload).__name__,
            sorted(payload.keys()) if isinstance(payload, dict) else None,
        )
        if not payload:
            raise HTTPException(status_code=404, detail='Match statistics not found')

        shape_summary = summarize_stats_payload_shape(payload)
        logger.info('AllSports stats normalized shape match_id=%s summary=%s', match_id, shape_summary)
        return AllSportsStatsResponse(**normalize_match_stats(match_id, payload))
    except AllSportsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except StatsPayloadShapeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                'code': exc.code,
                'message': exc.message,
                'details': exc.details,
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Unexpected AllSports stats error match_id=%s error=%s', match_id, exc)
        raise HTTPException(status_code=500, detail='Unexpected error while processing match statistics') from exc




def _build_sportsapipro_client() -> SportsAPIProClient:
    try:
        return SportsAPIProClient.from_env()
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/games/current', response_model=SportsAPIProGamesResponse)
def sportsapipro_games_current() -> SportsAPIProGamesResponse:
    client = _build_sportsapipro_client()
    try:
        payload = client.get_games_current()
        return SportsAPIProGamesResponse(games=normalize_sportsapipro_games(payload))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/games/results', response_model=SportsAPIProGamesResponse)
def sportsapipro_games_results(date: str | None = None) -> SportsAPIProGamesResponse:
    if date:
        _parse_iso_date(date)
    client = _build_sportsapipro_client()
    try:
        payload = client.get_games_results(game_date=date)
        return SportsAPIProGamesResponse(games=normalize_sportsapipro_games(payload))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/game/{game_id}', response_model=SportsAPIProGamesResponse)
def sportsapipro_game(game_id: str) -> SportsAPIProGamesResponse:
    if not game_id.strip():
        raise HTTPException(status_code=400, detail='game_id is required')
    client = _build_sportsapipro_client()
    try:
        payload = client.get_game(game_id)
        return SportsAPIProGamesResponse(games=normalize_sportsapipro_games(payload))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/athlete/{athlete_id}/games')
def sportsapipro_athlete_games(athlete_id: str) -> dict[str, object]:
    if not athlete_id.strip():
        raise HTTPException(status_code=400, detail='athlete_id is required')
    client = _build_sportsapipro_client()
    try:
        return {'athleteId': athlete_id, 'payload': client.get_athlete_games(athlete_id)}
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/athlete/{athlete_id}/game-log-normalized', response_model=SportsAPIProAthleteGameLogsResponse)
def sportsapipro_athlete_games_normalized(athlete_id: str) -> SportsAPIProAthleteGameLogsResponse:
    if not athlete_id.strip():
        raise HTTPException(status_code=400, detail='athlete_id is required')
    client = _build_sportsapipro_client()
    try:
        payload = client.get_athlete_games(athlete_id)
        logs = normalize_athlete_game_logs(athlete_id, payload)
        return SportsAPIProAthleteGameLogsResponse(athleteId=athlete_id, logs=logs)
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc
    except SportsAPIProNormalizeError as exc:
        raise HTTPException(status_code=422, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc


@app.get('/api/sportsapipro/search')
def sportsapipro_search(q: str) -> dict[str, object]:
    if not q.strip():
        raise HTTPException(status_code=400, detail='q is required')
    client = _build_sportsapipro_client()
    try:
        return {'query': q, 'payload': client.search(q)}
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message, 'details': exc.details}) from exc

@app.get('/api/providers/capabilities', response_model=ProviderCapabilitiesResponse)
def provider_capabilities() -> ProviderCapabilitiesResponse:
    return ProviderCapabilitiesResponse(providers={'allsports': ALLSPORTS_PROVIDER_CAPABILITIES, 'sportsapipro': SPORTSAPIPRO_PROVIDER_CAPABILITIES})


@app.get('/api/allsports/match/{match_id}/stats/debug')
def allsports_match_stats_debug(match_id: str) -> dict[str, object]:
    if not match_id.strip():
        raise HTTPException(status_code=400, detail='match_id is required')
    client = _build_allsports_client()
    try:
        payload = client.get_match_statistics(match_id)
        logger.info(
            'AllSports stats upstream payload match_id=%s top_level_type=%s top_level_keys=%s',
            match_id,
            type(payload).__name__,
            sorted(payload.keys()) if isinstance(payload, dict) else None,
        )
        if not payload:
            raise HTTPException(status_code=404, detail='Match statistics not found')

        payload_shape = summarize_stats_payload_shape(payload)
        response: dict[str, object] = {
            'payloadShape': payload_shape,
            'topLevelType': type(payload).__name__,
            'topLevelKeys': sorted(payload.keys()) if isinstance(payload, dict) else None,
        }

        try:
            normalized = normalize_match_stats(match_id, payload)
            response.update({
                'matchId': normalized['matchId'],
                'normalizedPreview': {
                    'homeTeam': normalized.get('homeTeam'),
                    'awayTeam': normalized.get('awayTeam'),
                    'teamStatsCount': len(normalized.get('teamStats') or []),
                    'playerStatsPresent': normalized.get('playerStats') is not None,
                    'playerStatsCount': len(normalized.get('playerStats') or []),
                },
            })
        except StatsPayloadShapeError as exc:
            response.update({
                'matchId': match_id,
                'normalizedPreview': None,
                'normalizationError': {
                    'code': exc.code,
                    'message': exc.message,
                    'details': exc.details,
                },
            })
        return response
    except AllSportsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Unexpected AllSports stats debug error match_id=%s error=%s', match_id, exc)
        return {
            'matchId': match_id,
            'normalizedPreview': None,
            'normalizationError': {
                'code': 'stats_debug_unexpected_error',
                'message': 'Unexpected error while inspecting match statistics payload',
                'details': {'exception_type': type(exc).__name__},
            },
        }


@app.get('/api/allsports/match/{match_id}/stats/raw')
def allsports_match_stats_raw(match_id: str) -> dict[str, object]:
    if not match_id.strip():
        raise HTTPException(status_code=400, detail='match_id is required')

    client = _build_allsports_client()
    try:
        payload = client.get_match_statistics(match_id)
        logger.info(
            'AllSports stats upstream payload match_id=%s top_level_type=%s top_level_keys=%s',
            match_id,
            type(payload).__name__,
            sorted(payload.keys()) if isinstance(payload, dict) else None,
        )
        if not payload:
            raise HTTPException(status_code=404, detail='Match statistics not found')

        first_item_keys = None
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            first_item_keys = sorted(payload[0].keys())

        return {
            'matchId': match_id,
            'top_level_type': type(payload).__name__,
            'top_level_keys': sorted(payload.keys()) if isinstance(payload, dict) else None,
            'list_length': len(payload) if isinstance(payload, list) else None,
            'first_item_keys': first_item_keys,
            'preview': safe_payload_preview(payload),
        }
    except AllSportsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Unexpected AllSports stats raw inspection error match_id=%s error=%s', match_id, exc)
        raise HTTPException(status_code=500, detail='Unexpected error while inspecting raw match statistics') from exc



@app.get('/api/sportsapipro/games/current', response_model=SportsAPIProGamesResponse)
def sportsapipro_games_current() -> SportsAPIProGamesResponse:
    client = _build_sportsapipro_client()
    try:
        return SportsAPIProGamesResponse(games=normalize_games_payload(client.get_current_games()))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get('/api/sportsapipro/games/results', response_model=SportsAPIProGamesResponse)
def sportsapipro_games_results() -> SportsAPIProGamesResponse:
    client = _build_sportsapipro_client()
    try:
        return SportsAPIProGamesResponse(games=normalize_games_payload(client.get_game_results()))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get('/api/sportsapipro/game/{game_id}', response_model=SportsAPIProGamesResponse)
def sportsapipro_game(game_id: str) -> SportsAPIProGamesResponse:
    if not game_id.strip():
        raise HTTPException(status_code=400, detail='game_id is required')
    client = _build_sportsapipro_client()
    try:
        return SportsAPIProGamesResponse(games=normalize_games_payload(client.get_game(game_id.strip())))
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get('/api/sportsapipro/athlete/{athlete_id}/games')
def sportsapipro_athlete_games_raw(athlete_id: str) -> dict[str, object]:
    if not athlete_id.strip():
        raise HTTPException(status_code=400, detail='athlete_id is required')
    client = _build_sportsapipro_client()
    try:
        payload = client.get_athlete_games(athlete_id.strip())
        if isinstance(payload, dict):
            return payload
        return {'rows': payload}
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get('/api/sportsapipro/athlete/{athlete_id}/game-log-normalized', response_model=SportsAPIProAthleteGamesResponse)
def sportsapipro_athlete_games_normalized(athlete_id: str) -> SportsAPIProAthleteGamesResponse:
    if not athlete_id.strip():
        raise HTTPException(status_code=400, detail='athlete_id is required')
    client = _build_sportsapipro_client()
    try:
        payload = client.get_athlete_games(athlete_id.strip())
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return SportsAPIProAthleteGamesResponse(athleteId=athlete_id.strip(), logs=normalize_athlete_games_payload(athlete_id.strip(), payload))


@app.get('/api/sportsapipro/search')
def sportsapipro_search(q: str) -> dict[str, object]:
    if not q.strip():
        raise HTTPException(status_code=400, detail='q is required')
    client = _build_sportsapipro_client()
    try:
        payload = client.search(q.strip())
        if isinstance(payload, dict):
            return payload
        return {'results': payload}
    except SportsAPIProError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get('/allsports-test', response_class=HTMLResponse)
def allsports_test_page() -> HTMLResponse:
    html = '''<!doctype html>
<html>
<head>
  <title>Provider Test Page</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:24px;max-width:1000px;color:#0f172a;}
    input,button{padding:8px 10px;border-radius:8px;border:1px solid #cbd5e1;}
    button{cursor:pointer;background:#0f172a;color:#fff;border-color:#0f172a;}
    .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
    .layout{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;}
    ul{padding-left:18px;}
    li{margin-bottom:8px;cursor:pointer;}
    pre{background:#f8fafc;padding:12px;border-radius:10px;overflow:auto;max-height:600px;}
  </style>
</head>
<body>
  <h1>Provider API Test</h1>
  <div class='row'>
    <label for='providerInput'>Provider:</label>
    <select id='providerInput'><option value='allsports'>AllSports</option><option value='sportsapipro'>SportsAPI Pro</option></select>
  </div>
  <div class='row'>
    <label for='dateInput'>Date:</label>
    <input id='dateInput' type='date'>
    <label for='providerInput'>Provider:</label>
    <select id='providerInput'><option value='allsports'>AllSports</option><option value='sportsapipro'>SportsAPI Pro</option></select>
    <button id='loadGamesBtn'>Load Games</button>
    <input id='athleteInput' placeholder='Athlete ID (SportsAPI Pro)'>
    <button id='loadAthleteBtn'>Load Athlete Logs</button>
  </div>
  <p id='msg'></p>
  <div class='layout'>
    <div>
      <h3>Games</h3>
      <ul id='games'></ul>
    </div>
    <div>
      <h3>Response</h3>
      <pre id='stats'>{}</pre>
    </div>
  </div>
  <script>
    const msg = document.getElementById('msg');
    const gamesEl = document.getElementById('games');
    const statsEl = document.getElementById('stats');
    const dateInput = document.getElementById('dateInput');
    const providerInput = document.getElementById('providerInput');
    const athleteInput = document.getElementById('athleteInput');
    const today = new Date().toISOString().slice(0, 10);
    dateInput.value = today;

    async function loadGames() {
      const date = dateInput.value;
      gamesEl.innerHTML = '';
      statsEl.textContent = '{}';
      msg.textContent = 'Loading games...';
      const provider = providerInput.value;
      const resp = provider === 'sportsapipro'
        ? await fetch(`/api/sportsapipro/games/results?date=${encodeURIComponent(date)}`)
        : await fetch(`/api/allsports/games?date=${encodeURIComponent(date)}`);
      const url = provider === 'sportsapipro'
        ? '/api/sportsapipro/games/current'
        : `/api/allsports/games?date=${encodeURIComponent(date)}`;
      const resp = await fetch(url);
      const data = await resp.json();
      if (!resp.ok) {
        msg.textContent = `Error: ${typeof data.detail === 'object' ? data.detail.message : (data.detail || 'Failed to load games')}`;
        return;
      }
      msg.textContent = `Loaded ${data.games.length} game(s). Click one to inspect stats.`;
      for (const game of data.games) {
      msg.textContent = `Loaded ${(data.games || []).length} game(s). Click one to inspect response.`;
      for (const game of (data.games || [])) {
        const li = document.createElement('li');
        li.textContent = `${game.awayTeam || 'Away'} @ ${game.homeTeam || 'Home'} (${game.id})`;
        li.addEventListener('click', () => loadStats(game.id));
        gamesEl.appendChild(li);
      }
    }

    async function loadStats(matchId) {
      statsEl.textContent = 'Loading...';
      const provider = providerInput.value;
      const resp = provider === 'sportsapipro'
        ? await fetch(`/api/sportsapipro/game/${encodeURIComponent(matchId)}`)
        : await fetch(`/api/allsports/match/${encodeURIComponent(matchId)}/stats`);
      const url = provider === 'sportsapipro'
        ? `/api/sportsapipro/game/${encodeURIComponent(matchId)}`
        : `/api/allsports/match/${encodeURIComponent(matchId)}/stats`;
      const resp = await fetch(url);
      const data = await resp.json();
      statsEl.textContent = JSON.stringify(data, null, 2);
    }

    async function loadAthlete(){
      if(providerInput.value !== 'sportsapipro'){
        msg.textContent='Switch provider to SportsAPI Pro for athlete logs.';
        return;
      }
      const athleteId = athleteInput.value.trim();
      if(!athleteId){ msg.textContent='Enter athlete ID.'; return; }
      statsEl.textContent = 'Loading...';
      const resp = await fetch(`/api/sportsapipro/athlete/${encodeURIComponent(athleteId)}/game-log-normalized`);
      const data = await resp.json();
      statsEl.textContent = JSON.stringify(data, null, 2);
    }

    document.getElementById('loadGamesBtn').addEventListener('click', loadGames);
    document.getElementById('loadAthleteBtn').addEventListener('click', loadAthlete);
  </script>
</body>
</html>'''
    return HTMLResponse(html)


@app.get('/', response_class=HTMLResponse)
def public_home_page() -> HTMLResponse:
    html = """<!doctype html><html><head><title>ParlayBot</title><style>body{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:760px;color:#0f172a;}h1{margin:0 0 10px;}p{margin:0 0 18px;color:#475569;}.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;}a{text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:700;}.cta{background:#0f172a;color:#fff;}.secondary{border:1px solid #cbd5e1;color:#0f172a;}</style></head><body><h1>Did This Parlay Cash?</h1><p>Paste your bet slip and instantly see if it hit.</p><div class='actions'><a class='cta' href='/check'>Check a Slip</a></div></body></html>"""
    return HTMLResponse(html)


@app.get('/check', response_class=HTMLResponse)
def public_check_page() -> HTMLResponse:
    html = '''<!doctype html>
<html>
<head>
  <title>Did This Parlay Cash?</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:900px;color:#0f172a;}
    h1{margin-bottom:8px;}
    p{color:#475569;}
    textarea{width:100%;min-height:190px;padding:12px;border:1px solid #cbd5e1;border-radius:10px;font-family:inherit;box-sizing:border-box;}
    button{margin-top:12px;padding:10px 14px;border:1px solid #334155;border-radius:10px;background:#0f172a;color:#fff;cursor:pointer;}
    button[disabled]{opacity:.6;cursor:not-allowed;}
    button.sample{margin-top:0;background:#fff;color:#0f172a;border:1px solid #cbd5e1;padding:8px 10px;}
    button.secondary{background:#fff;color:#0f172a;border-color:#cbd5e1;}
    #samples{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px;}
    #uploadWrap{margin-top:12px;padding:10px;border:1px dashed #cbd5e1;border-radius:10px;background:#fafafa;}
    #message{margin-top:12px;color:#334155;font-weight:600;}
    #resultWrap{margin-top:14px;border:1px solid #e2e8f0;border-radius:12px;padding:14px;}
    #overall{font-size:18px;font-weight:700;margin-bottom:12px;}
    #summaryWrap{margin-top:12px;}
    #summaryOut{min-height:98px;background:#f8fafc;}
    table{width:100%;border-collapse:collapse;}
    th,td{text-align:left;padding:8px;border-bottom:1px solid #e2e8f0;vertical-align:top;}
    th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:#64748b;}
    code{background:#f8fafc;padding:2px 6px;border-radius:6px;}
  </style>
</head>
<body>
  <h1>Did This Parlay Cash?</h1>
  <p>One leg per line. Pick a sample, paste your slip, or upload a screenshot, then hit <code>Check Slip</code>.</p>
  <div id='samples'>
    <button type='button' class='sample' data-sample='sample_nba_props'>NBA Props</button>
    <button type='button' class='sample' data-sample='sample_mlb'>MLB Mix</button>
    <button type='button' class='sample' data-sample='sample_nfl'>NFL Mix</button>
  </div>
  <form id='checkForm'>
  <textarea id='slip' placeholder='Jokic over 24.5 points
Denver ML
Murray over 2.5 threes'></textarea>
  <input id='stakeAmount' type='number' min='0.01' step='0.01' placeholder='Stake amount (optional)' style='margin-top:10px;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:10px;box-sizing:border-box;'>
  <label for='slipDate' style='display:block;margin-top:10px;font-weight:700;'>Bet Date</label>
  <input id='slipDate' type='date' placeholder='Bet Date (optional, recommended)' style='margin-top:6px;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:10px;box-sizing:border-box;'>
  <div style='font-size:12px;color:#64748b;margin-top:4px;'>Optional, but strongly recommended for NBA player props.</div>
  <label style='display:flex;align-items:center;gap:8px;margin-top:10px;'>
    <input id='searchHistorical' type='checkbox' style='width:auto;'>
    <span>Search historical results</span>
  </label>
  <div id='uploadWrap'>
    <label for='slipImage'><strong>Or upload a slip screenshot</strong></label>
    <input id='slipImage' type='file' accept='image/*'>
  </div>
  <button id='checkBtn' type='submit'>Check Slip</button>
  </form>
  <div id='message'></div>
  <div id='resultWrap' hidden>
    <div id='overall'></div>
    <div id='payoutOut' style='margin:8px 0;color:#334155;'></div>
    <div id='debugOut' style='margin:8px 0 12px;color:#334155;'></div>
    <table>
      <thead><tr><th>Leg</th><th>Result</th><th>Matched event</th></tr></thead>
      <tbody id='legsBody'></tbody>
    </table>
    <div id='summaryWrap'>
      <button id='copyBtn' class='secondary' type='button' disabled>Copy Summary</button>
      <textarea id='summaryOut' readonly placeholder='Summary will appear here after checking a slip.'></textarea>
    </div>
  </div>
  <script>
    const sampleSlips={
      sample_nba_props:'Jokic over 24.5 points\\nMurray over 2.5 threes\\nDenver ML',
      sample_mlb:'Dodgers ML\\nYankees +1.5\\nGame Total Over 8.5',
      sample_nfl:'Chiefs ML\\nMahomes over 265.5 passing yards\\nKelce over 68.5 receiving yards'
    };
    const form=document.getElementById('checkForm');
    const slip=document.getElementById('slip');
    const stakeAmount=document.getElementById('stakeAmount');
    const slipImage=document.getElementById('slipImage');
    const slipDate=document.getElementById('slipDate');
    const searchHistorical=document.getElementById('searchHistorical');
    const btn=document.getElementById('checkBtn');
    const copyBtn=document.getElementById('copyBtn');
    const summaryOut=document.getElementById('summaryOut');
    const msg=document.getElementById('message');
    const wrap=document.getElementById('resultWrap');
    const overall=document.getElementById('overall');
    const payoutOut=document.getElementById('payoutOut');
    const debugOut=document.getElementById('debugOut');
    const legsBody=document.getElementById('legsBody');
    const resultLabel={win:'Win',loss:'Loss',pending:'Pending',push:'Push',void:'Void',review:'Review',unmatched:'Review'};
    const resultEmoji={win:'✅',loss:'❌',pending:'⏳',push:'➖',void:'🚫',review:'🧐',unmatched:'🧐'};
    const overallLabel={cashed:'CASHED',lost:'LOST',still_live:'STILL LIVE',needs_review:'NEEDS REVIEW'};
    const emptyTextMessage='Paste at least one leg first.';
    let selectedGameByLegId={};

    slip.addEventListener('input',()=>{
      selectedGameByLegId={};
    });
    document.querySelectorAll('[data-sample]').forEach((node)=>{
      node.addEventListener('click',()=>{
        const key=node.getAttribute('data-sample');
        slip.value=sampleSlips[key]||'';
        slip.focus();
      });
    });

    function renderRows(legs){
      legsBody.innerHTML='';
      for(const [index,item] of (legs||[]).entries()){
        const legId=String(item.leg_id ?? index);
        const tr=document.createElement('tr');
        const legCell=document.createElement('td');
        const resultCell=document.createElement('td');
        const eventCell=document.createElement('td');
        const legText=document.createElement('div');
        legText.textContent=item.leg||'—';
        legCell.appendChild(legText);

        const detailsWrap=document.createElement('details');
        detailsWrap.style.marginTop='6px';
        const detailsSummary=document.createElement('summary');
        detailsSummary.textContent='Details';
        detailsSummary.style.cursor='pointer';
        detailsSummary.style.color='#475569';
        detailsSummary.style.fontSize='12px';
        detailsWrap.appendChild(detailsSummary);

        const detailsBody=document.createElement('div');
        detailsBody.style.marginTop='6px';
        detailsBody.style.fontSize='12px';
        detailsBody.style.color='#334155';
        const componentValues=item.component_values||{};
        const componentRows=Object.keys(componentValues).map((key)=>`<div>${key}: ${componentValues[key]}</div>`).join('');
        const boxscoreText=(item.player_found_in_boxscore===null||item.player_found_in_boxscore===undefined)
          ? 'Unknown'
          : (item.player_found_in_boxscore ? 'Yes' : 'No');
        detailsBody.innerHTML=`
          <div>Parsed: ${item.parsed_player_or_team||'—'} / ${item.normalized_market||'—'}</div>
          <div>Matched event: ${item.matched_event||'—'}</div>
          <div>Stat used: ${item.normalized_market||'—'}</div>
          <div>Line: ${item.line ?? '—'}</div>
          <div>Actual: ${item.actual_value ?? '—'}</div>
          ${componentRows}
          <div>Result: ${resultLabel[item.result]||String(item.result||'review')}</div>
          <div>Reason: ${item.explanation_reason||'—'}</div>
          <div>Player in box score: ${boxscoreText}</div>
        `;
        detailsWrap.appendChild(detailsBody);
        legCell.appendChild(detailsWrap);

        resultCell.textContent=resultLabel[item.result]||String(item.result||'review');
        const candidateGames=(item.candidate_games||[]);

        if(candidateGames.length>0){
          const select=document.createElement('select');
          const prompt=document.createElement('option');
          prompt.value='';
          prompt.textContent='Auto-match (clear manual selection)';
          select.appendChild(prompt);
          for(const game of candidateGames){
            const opt=document.createElement('option');
            opt.value=game.event_id;
            opt.textContent=game.event_label;
            if(game.event_id===selectedGameByLegId[legId]){ opt.selected=true; }
            select.appendChild(opt);
          }
          select.addEventListener('change',()=>{
            const nextValue=select.value||'';
            if(nextValue){
              selectedGameByLegId={...selectedGameByLegId,[legId]:nextValue};
            }else{
              const nextSelection={...selectedGameByLegId};
              delete nextSelection[legId];
              selectedGameByLegId=nextSelection;
            }
            submitCheck();
          });
          eventCell.appendChild(select);
          if(item.explanation_reason){
            const reviewNote=document.createElement('div');
            reviewNote.style.marginTop='6px';
            reviewNote.style.fontSize='12px';
            reviewNote.style.color='#475569';
            reviewNote.textContent=`Review reason: ${item.explanation_reason}`;
            eventCell.appendChild(reviewNote);
          }
          if(item.matched_event){
            const matched=document.createElement('div');
            matched.style.marginTop='6px';
            matched.style.fontSize='12px';
            matched.style.color='#475569';
            matched.textContent=`Matched: ${item.matched_event}`;
            eventCell.appendChild(matched);
          }

          const resetBtn=document.createElement('button');
          resetBtn.type='button';
          resetBtn.className='secondary';
          resetBtn.style.marginTop='6px';
          resetBtn.textContent='Reset selection';
          resetBtn.disabled=!selectedGameByLegId[legId];
          resetBtn.addEventListener('click',()=>{
            const nextSelection={...selectedGameByLegId};
            delete nextSelection[legId];
            selectedGameByLegId=nextSelection;
            submitCheck();
          });
          eventCell.appendChild(resetBtn);
        }else if(item.matched_event){
          eventCell.textContent=item.matched_event;
        }else{
          eventCell.textContent=item.review_reason ? `Review: ${item.review_reason}` : (item.explanation_reason ? `Review: ${item.explanation_reason}` : '—');
        }
        tr.appendChild(legCell);
        tr.appendChild(resultCell);
        tr.appendChild(eventCell);
        legsBody.appendChild(tr);
      }
    }


    function buildSummary(payload){
      const lines=(payload.legs||[]).map((item)=>`${item.leg} ${resultEmoji[item.result]||'🧐'}`);
      lines.push('');
      lines.push(`Parlay: ${overallLabel[payload.parlay_result]||'NEEDS REVIEW'}`);
      return lines.join('\\n');
    }

    function normalizeScreenshotPayload(body){
      const parsedFromScreenshot=body.parsed_screenshot||{};
      const parsedLegObjects=parsedFromScreenshot.parsed_legs||[];
      const parsedLegs=parsedLegObjects.map((item)=>item.normalized_label||item.raw_leg_text||'—');
      const allReview=parsedLegs.length>0&&(body.result?.legs||[]).every((item)=>item.settlement==='unmatched');
      const extracted=(body.extracted_text||'').trim();
      const parseWarnings=parsedFromScreenshot.parse_warnings||[];
      const parseWarning=parseWarnings.length
        ?parseWarnings.join(' | ')
        :(parsedLegs.length===0
          ?(extracted
            ?'OCR text was extracted but it was not parseable into bet legs. Try a clearer screenshot.'
            :'No valid bet legs were detected from this input.')
          :null);
      return {
        ok:true,
        extracted_text:body.extracted_text||'',
        parsed_legs:parsedLegs,
        parsed_leg_objects:parsedLegObjects,
        detected_bet_date:parsedFromScreenshot.detected_bet_date||null,
        parse_warning:parseWarning,
        grading_warning:allReview?'Parsed legs were detected, but ESPN matching could not settle any leg.':null,
        legs:(body.result?.legs||[]).map((item)=>({
          leg:item.leg?.raw_text||'—',
          result:(item.settlement==='unmatched'?'review':item.settlement),
          matched_event:item.matched_event||item.leg?.event_label||null,
          candidate_games:item.candidate_games||item.leg?.event_candidates||[],
          parsed_player_or_team:item.leg?.player||item.leg?.team||null,
          normalized_market:item.normalized_market||null,
          line:item.line,
          actual_value:item.actual_value,
          component_values:item.component_values||null,
          explanation_reason:item.explanation_reason||null,
          review_reason:item.review_reason||item.explanation_reason||null,
          candidate_events:item.candidate_events||item.candidate_games||item.leg?.event_candidates||[],
          resolved_player_name:item.resolved_player_name||item.leg?.resolved_player_name||null,
          resolved_team:item.resolved_team||item.leg?.resolved_team||null,
          selected_bet_date:item.selected_bet_date||item.leg?.selected_bet_date||null,
          player_found_in_boxscore:item.player_found_in_boxscore,
        })),
        parlay_result:(body.result?.overall==='pending'?'still_live':(body.result?.overall||'needs_review')),
      };
    }

    async function submitCheck(){
      const text=slip.value.trim();
      const file=slipImage.files&&slipImage.files[0];
      wrap.hidden=true;
      legsBody.innerHTML='';
      debugOut.innerHTML='';
      copyBtn.disabled=true;
      summaryOut.value='';
      if(!text&&!file){msg.textContent='Paste at least one leg first, or upload a screenshot.';return;}
      if(file&&file.type&&!file.type.startsWith('image/')){msg.textContent='Please upload an image file for screenshot grading.';return;}
      if(file&&file.size>8*1024*1024){msg.textContent='Screenshot is too large. Please use an image under 8MB.';return;}

      btn.disabled=true;
      msg.textContent='Checking your slip...';
      try{
        let data;
        let res;
        if(file){
          const form=new FormData();
          form.append('file',file);
          if(slipDate.value){form.append('bet_date', slipDate.value);}
          res=await fetch('/ingest/screenshot/grade',{method:'POST',body:form});
          const body=await res.json();
          if(!res.ok){msg.textContent=body.detail||body.message||'Could not check this screenshot right now.';return;}
          data=normalizeScreenshotPayload(body);
          if(data.parsed_legs&&data.parsed_legs.length){slip.value=data.parsed_legs.join('\n');}
          if(!slipDate.value&&data.detected_bet_date){slipDate.value=data.detected_bet_date;}
        }else{
          const stakeRaw=(stakeAmount.value||'').trim();
          const payload={text};
          if(stakeRaw){payload.stake_amount=stakeRaw;}
          if(slipDate.value){payload.bet_date=slipDate.value; payload.date_of_slip=slipDate.value;}
          if(searchHistorical.checked){payload.search_historical=true;}
          if(Object.keys(selectedGameByLegId).length){payload.selected_event_by_leg_id=selectedGameByLegId;}
          res=await fetch('/check-slip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          data=await res.json();
        }

        if(!res.ok){msg.textContent=data.detail||data.message||'Could not check this slip right now.';return;}
        msg.textContent=data.message||'Done.';
        overall.textContent='Parlay result: '+(overallLabel[data.parlay_result]||'NEEDS REVIEW');
        if(data.estimated_payout!==undefined&&data.estimated_profit!==undefined){
          payoutOut.textContent=`Estimated payout: $${Number(data.estimated_payout).toFixed(2)} (profit: $${Number(data.estimated_profit).toFixed(2)})`;
        }else{
          payoutOut.textContent='';
        }
        renderRows(data.legs||[]);
        const extracted=(data.extracted_text||'').trim();
        const parsedLegs=(data.parsed_legs||[]).filter(Boolean);
        const parseWarning=data.parse_warning?`<div><strong>Parsing:</strong> ${data.parse_warning}</div>`:'';
        const gradingWarning=data.grading_warning?`<div><strong>Grading:</strong> ${data.grading_warning}</div>`:'';
        debugOut.innerHTML=`
          ${extracted?`<div><strong>OCR extracted text:</strong><pre style="white-space:pre-wrap;background:#f8fafc;padding:8px;border-radius:8px;">${extracted.replace(/</g,'&lt;')}</pre></div>`:''}
          <div><strong>Parsed legs before grading:</strong> ${parsedLegs.length?parsedLegs.join(' | '):'No valid bet legs were detected from this input.'}</div>
          ${parseWarning}
          ${gradingWarning}
        `;
        summaryOut.value=buildSummary(data);
        copyBtn.disabled=false;
        wrap.hidden=false;
      }catch(err){
        msg.textContent='Could not check this slip right now.';
      }finally{
        btn.disabled=false;
      }
    }

    form.addEventListener('submit',async(event)=>{
      event.preventDefault();
      await submitCheck();
    });

    window.addEventListener('error',()=>{
      msg.textContent='Something went wrong in the page. Please refresh and try again.';
    });

    copyBtn.addEventListener('click',async()=>{
      const text=summaryOut.value.trim();
      if(!text){return;}
      try{
        await navigator.clipboard.writeText(text);
        msg.textContent='Summary copied.';
      }catch(err){
        summaryOut.focus();
        summaryOut.select();
        msg.textContent='Copy blocked. Summary selected for manual copy.';
      }
    });
  </script>
</body>
</html>'''
    return HTMLResponse(html)


def _estimate_profit_from_american(stake_amount: float, american_odds: int) -> float:
    if american_odds > 0:
        return round(stake_amount * (american_odds / 100.0), 2)
    return round(stake_amount * (100.0 / abs(american_odds)), 2)


def _process_public_check_text(
    text: str,
    stake_amount: float | None = None,
    date_of_slip: date | datetime | None = None,
    bet_date: date | None = None,
    search_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
) -> dict:
    normalized = text.strip()
    if stake_amount is not None and stake_amount <= 0:
        return {
            'ok': False,
            'message': 'Enter a stake greater than 0.',
            'legs': [],
            'parsed_legs': [],
            'parse_warning': None,
            'grading_warning': None,
            'parlay_result': 'needs_review',
        }
    if not normalized:
        return {
            'ok': False,
            'message': 'Paste at least one leg first.',
            'legs': [],
            'parsed_legs': [],
            'parse_warning': None,
            'grading_warning': None,
            'parlay_result': 'needs_review',
        }

    parsed_legs = [leg.raw_text for leg in parse_text(normalized)]
    if not parsed_legs:
        return {
            'ok': False,
            'message': 'No bet legs found. Try one leg per line.',
            'legs': [],
            'parsed_legs': [],
            'parse_warning': 'No valid bet legs were detected from this input.',
            'grading_warning': None,
            'parlay_result': 'needs_review',
        }

    try:
        graded = grade_text(
            normalized,
            provider=_public_check_provider,
            posted_at=date_of_slip,
            bet_date=bet_date,
            include_historical=search_historical,
            selected_event_id=selected_event_id,
            selected_event_by_leg_id=selected_event_by_leg_id,
        )
    except Exception:
        return {
            'ok': False,
            'message': 'Could not grade this slip right now.',
            'legs': [],
            'parsed_legs': parsed_legs,
            'parse_warning': None,
            'grading_warning': 'Parsed legs were detected, but grading did not complete.',
            'parlay_result': 'needs_review',
        }

    legs = []
    unmatched_count = 0
    ambiguous_count = 0
    for index, item in enumerate(graded.legs):
        result = item.settlement
        if item.settlement == 'unmatched':
            unmatched_count += 1
            result = 'review'
            if any('multiple possible games' in note.lower() for note in item.leg.notes):
                ambiguous_count += 1
        legs.append({
            'leg_id': str(index),
            'leg': item.leg.raw_text,
            'result': result,
            'matched_event': item.matched_event or item.leg.event_label,
            'candidate_games': item.candidate_games or item.leg.event_candidates,
            'parsed_player_or_team': item.leg.player or item.leg.team,
            'normalized_market': item.normalized_market,
            'line': item.line,
            'actual_value': item.actual_value,
            'component_values': item.component_values,
            'explanation_reason': item.explanation_reason,
            'review_reason': item.review_reason,
            'candidate_events': item.candidate_events or item.candidate_games or item.leg.event_candidates,
            'resolved_player_name': item.resolved_player_name or item.leg.resolved_player_name,
            'resolved_team': item.resolved_team or item.leg.resolved_team,
            'selected_bet_date': item.selected_bet_date or item.leg.selected_bet_date,
            'player_found_in_boxscore': item.player_found_in_boxscore,
        })

    parlay_result = 'still_live' if graded.overall == 'pending' else graded.overall
    out = {
        'ok': True,
        'message': 'Slip checked.',
        'legs': legs,
        'parsed_legs': parsed_legs,
        'parse_warning': None,
        'grading_warning': None,
        'parlay_result': parlay_result,
    }
    if unmatched_count == len(legs):
        out['message'] = 'Could not confidently match this slip to settled results. Please review manually.'
        out['grading_warning'] = 'Parsed legs were detected, but ESPN matching could not settle any leg.'
    elif unmatched_count > 0:
        out['message'] = f'{unmatched_count} leg(s) need manual review.'
        out['grading_warning'] = f'ESPN matching could not settle {unmatched_count} parsed leg(s).'

    if ambiguous_count > 0:
        out['grading_warning'] = 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'

    if stake_amount is not None:
        financials = extract_financials(normalized)
        if financials.american_odds is None:
            return {
                'ok': False,
                'message': 'Add odds in your slip text (for example +120) to estimate payout.',
                'legs': [],
                'parsed_legs': parsed_legs,
                'parse_warning': None,
                'grading_warning': out.get('grading_warning'),
                'parlay_result': 'needs_review',
            }
        est_profit = _estimate_profit_from_american(stake_amount, financials.american_odds)
        out['stake_amount'] = round(stake_amount, 2)
        out['estimated_profit'] = est_profit
        out['estimated_payout'] = round(stake_amount + est_profit, 2)
        out['american_odds_used'] = financials.american_odds
    return out


def _run_public_check_job(job_id: str, text: str, stake_amount: float | None = None) -> None:
    try:
        result = _process_public_check_text(text, stake_amount=stake_amount)
        with _public_check_jobs_lock:
            row = _public_check_jobs.get(job_id)
            if row is None:
                return
            row['status'] = 'complete'
            row['result'] = result
            row['error'] = None
            row['completed_at'] = time.time()
    except Exception as exc:
        with _public_check_jobs_lock:
            row = _public_check_jobs.get(job_id)
            if row is None:
                return
            row['status'] = 'failed'
            row['result'] = None
            row['error'] = str(exc)
            row['completed_at'] = time.time()


@app.post('/check')
@app.post('/check-slip')
def public_check_slip(request: Request, response: Response, payload: dict = Body(...)):
    _enforce_public_check_rate_limit(request, response, 'check-slip')
    stake = payload.get('stake_amount')
    if stake is None or stake == '':
        parsed_stake = None
    else:
        try:
            parsed_stake = float(stake)
        except (TypeError, ValueError):
            return {'ok': False, 'message': 'Enter a valid numeric stake amount.', 'legs': [], 'parsed_legs': [], 'parse_warning': None, 'grading_warning': None, 'parlay_result': 'needs_review'}

    raw_date = str(payload.get('bet_date') or payload.get('date_of_slip') or '').strip()
    parsed_date: date | None = None
    if raw_date:
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            return {'ok': False, 'message': 'Enter a valid date of slip.', 'legs': [], 'parsed_legs': [], 'parse_warning': None, 'grading_warning': None, 'parlay_result': 'needs_review'}

    selected_by_leg_payload = payload.get('selected_event_by_leg_id')
    if isinstance(selected_by_leg_payload, dict):
        selected_event_by_leg_id = {str(key): str(value) for key, value in selected_by_leg_payload.items() if str(value).strip()}
    else:
        selected_event_by_leg_id = {}

    return _process_public_check_text(
        str(payload.get('text', '')),
        stake_amount=parsed_stake,
        date_of_slip=parsed_date,
        bet_date=parsed_date,
        search_historical=bool(payload.get('search_historical', False)),
        selected_event_id=(str(payload.get('selected_event_id') or '').strip() or None),
        selected_event_by_leg_id=selected_event_by_leg_id,
    )


@app.post('/check/jobs', response_model=CheckJobCreateResponse)
def submit_public_check_job(request: Request, response: Response, payload: dict = Body(...)) -> CheckJobCreateResponse:
    _enforce_public_check_rate_limit(request, response, 'check-job')
    text = str(payload.get('text', '')).strip()
    if not text:
        raise HTTPException(status_code=400, detail='Paste at least one leg first.')
    stake = payload.get('stake_amount')
    if stake is None or stake == '':
        parsed_stake = None
    else:
        try:
            parsed_stake = float(stake)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail='Enter a valid numeric stake amount.')

    job_id = uuid4().hex
    with _public_check_jobs_lock:
        _cleanup_public_check_jobs()
        _public_check_jobs[job_id] = {
            'status': 'pending',
            'submitted_at': time.time(),
            'completed_at': None,
            'result': None,
            'error': None,
        }

    worker = threading.Thread(target=_run_public_check_job, args=(job_id, text, parsed_stake), daemon=True)
    worker.start()
    return CheckJobCreateResponse(job_id=job_id, status='pending')


@app.get('/check/jobs/{job_id}', response_model=CheckJobStatusResponse)
def get_public_check_job(job_id: str) -> CheckJobStatusResponse:
    with _public_check_jobs_lock:
        row = _public_check_jobs.get(job_id)
    if not row:
        raise HTTPException(status_code=404, detail='Job not found')

    status_value = row.get('status', 'failed')
    if status_value == 'complete':
        return CheckJobStatusResponse(job_id=job_id, status='complete', result=row.get('result'))
    if status_value == 'failed':
        return CheckJobStatusResponse(job_id=job_id, status='failed', error=(row.get('error') or 'Slip processing failed'))
    return CheckJobStatusResponse(job_id=job_id, status='pending')


@app.post('/auth/register', response_model=SessionResponse)
def register_endpoint(req: UserRegisterRequest, db: Session = Depends(get_db)) -> SessionResponse:
    username = req.username.strip().lower().lstrip('@')
    if len(username) < 3:
        raise HTTPException(status_code=400, detail='Username must be at least 3 characters')
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail='Password must be at least 6 characters')
    if get_user_by_username(db, username):
        raise HTTPException(status_code=409, detail='Username already exists')
    user = create_user(db, username=username, password_hash=hash_password(req.password), email=req.email, is_admin=False, role=req.role, linked_capper_username=req.linked_capper_username)
    if user.role == 'capper' and user.linked_capper_username:
        claim_capper_profile(db, user, user.linked_capper_username)
    session = create_user_session(db, user=user, session_token=create_session_token(), expires_at=session_expiry())
    return _session_to_response(session)


@app.post('/auth/login', response_model=SessionResponse)
def login_endpoint(req: UserLoginRequest, db: Session = Depends(get_db)) -> SessionResponse:
    user = get_user_by_username(db, req.username)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    session = create_user_session(db, user=user, session_token=create_session_token(), expires_at=session_expiry())
    return _session_to_response(session)


@app.get('/auth/me', response_model=UserProfileResponse)
def me_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session)) -> UserProfileResponse:
    return _user_to_response(session.user)


@app.post('/auth/logout', response_model=LogoutResponse)
def logout_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> LogoutResponse:
    revoke_user_session(db, session.session_token)
    return LogoutResponse(success=True)


@app.post('/admin/auth/login', response_model=SessionResponse)
def admin_login_endpoint(req: AdminLoginRequest, db: Session = Depends(get_db)) -> SessionResponse:
    user = get_user_by_username(db, req.username)
    if user is None:
        user = create_user(db, username=req.username, password_hash=hash_password(req.password), email=None, is_admin=True, role='admin')
    if not user.is_admin or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid admin credentials')
    session = create_user_session(db, user=user, session_token=create_session_token(), expires_at=session_expiry())
    return _session_to_response(session)


@app.get('/admin/auth/sessions', response_model=AdminSessionsResponse)
def admin_sessions_endpoint(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AdminSessionsResponse:
    rows = [AdminSessionRow(session_id=s.id, username=s.user.username, created_at=s.created_at, expires_at=s.expires_at, last_seen_at=s.last_seen_at, is_active=s.is_active) for s in list_admin_sessions(db)]
    return AdminSessionsResponse(rows=rows)


def _ops_page_html(title: str, api_path: str, requires_auth: bool = True) -> str:
    auth = "const token=localStorage.getItem('parlaybot_token')||''; const headers=token?{Authorization:`Bearer ${token}`}:{ };" if requires_auth else "const headers={};"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>body{{font-family:Arial,sans-serif;max-width:1000px;margin:40px auto;padding:0 16px}}pre{{background:#111;color:#eee;padding:16px;overflow:auto;border-radius:12px}}button{{padding:10px 14px;border-radius:10px;border:1px solid #ccc;background:#fff;cursor:pointer}}</style></head><body><h1>{title}</h1><p>Operational view backed by <code>{api_path}</code>.</p><button onclick='loadData()'>Refresh</button><pre id='out'>Loading...</pre><script>async function loadData(){{{auth} const res=await fetch('{api_path}',{{headers}}); const txt=await res.text(); try{{document.getElementById('out').textContent=JSON.stringify(JSON.parse(txt), null, 2);}}catch(e){{document.getElementById('out').textContent=txt;}}}} loadData();</script></body></html>"""


@app.get('/ops/billing', response_class=HTMLResponse)
def ops_billing_page() -> str:
    return _ops_page_html('Billing Ops', '/billing/history')


@app.get('/ops/emails', response_class=HTMLResponse)
def ops_emails_page() -> str:
    return _ops_page_html('Email Ops', '/billing/emails')


@app.get('/ops/affiliate-webhooks', response_class=HTMLResponse)
def ops_affiliate_webhooks_page() -> str:
    return _ops_page_html('Affiliate Webhook Ops', '/affiliate/webhooks')



@app.get('/app')
def frontend_app_page() -> RedirectResponse:
    return RedirectResponse(url='/check', status_code=307)


@app.get('/account')
def account_page() -> RedirectResponse:
    return RedirectResponse(url='/check', status_code=307)


@app.post('/admin/users/{user_id}/role', response_model=UserProfileResponse)
def admin_set_user_role_endpoint(user_id: int, req: UserRoleUpdateRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> UserProfileResponse:
    user = db.get(_db_models.UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    user = set_user_role(db, user, req.role, linked_capper_username=req.linked_capper_username)
    if user.role == 'capper' and user.linked_capper_username:
        claim_capper_profile(db, user, user.linked_capper_username)
    return _user_to_response(user)


@app.get('/capper/me', response_model=CapperSelfProfileResponse)
def capper_me_endpoint(session: _db_models.UserSessionORM = Depends(require_capper_session), db: Session = Depends(get_db)) -> CapperSelfProfileResponse:
    user = session.user
    if not user.linked_capper_username:
        raise HTTPException(status_code=400, detail='No linked capper profile')
    profile = claim_capper_profile(db, user, user.linked_capper_username)
    return CapperSelfProfileResponse(username=profile.username, is_public=profile.is_public, moderation_note=profile.moderation_note, claimed_by_user_id=profile.claimed_by_user_id, display_name=profile.display_name, bio=profile.bio, verified=profile.is_verified, verification_badge=profile.verification_badge)


@app.patch('/capper/me', response_model=CapperSelfProfileResponse)
def capper_me_update_endpoint(req: CapperSelfProfileUpdateRequest, session: _db_models.UserSessionORM = Depends(require_capper_session), db: Session = Depends(get_db)) -> CapperSelfProfileResponse:
    try:
        profile = update_capper_profile_self(db, session.user, display_name=req.display_name, bio=req.bio, is_public=req.is_public)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CapperSelfProfileResponse(username=profile.username, is_public=profile.is_public, moderation_note=profile.moderation_note, claimed_by_user_id=profile.claimed_by_user_id, display_name=profile.display_name, bio=profile.bio, verified=profile.is_verified, verification_badge=profile.verification_badge)


@app.get('/billing/entitlements', response_model=BillingEntitlementsResponse)
def billing_entitlements_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingEntitlementsResponse:
    payload = get_user_entitlements(db, session.user)
    return BillingEntitlementsResponse(**payload)


@app.post('/billing/stripe/checkout', response_model=SubscriptionCheckoutResponse)
def billing_stripe_checkout_endpoint(req: StripeCheckoutRequest, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> SubscriptionCheckoutResponse:
    try:
        sub, checkout_url = create_stripe_checkout(db, session.user, plan_code=req.plan_code, success_url=req.success_url, cancel_url=req.cancel_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SubscriptionCheckoutResponse(subscription_id=sub.id, plan_code=sub.plan_code, status=sub.status, provider=sub.provider, checkout_url=checkout_url)


@app.post('/billing/stripe/webhook', response_model=StripeWebhookResponse)
async def billing_stripe_webhook_endpoint(request: Request, stripe_signature: str | None = Header(default=None, alias='Stripe-Signature'), db: Session = Depends(get_db)) -> StripeWebhookResponse:
    raw = await request.body()
    if not verify_stripe_signature(raw, stripe_signature):
        raise HTTPException(status_code=401, detail='Invalid Stripe signature')
    payload = await request.json()
    evt = StripeWebhookEventRequest(**payload)
    processed, _sub = apply_stripe_event(db, evt.id, evt.type, payload)
    return StripeWebhookResponse(ok=True, processed=processed, event_id=evt.id, event_type=evt.type)


@app.get('/billing/plans', response_model=SubscriptionPlansResponse)
def billing_plans_endpoint(db: Session = Depends(get_db)) -> SubscriptionPlansResponse:
    rows = [SubscriptionPlanResponse(code=row.code, name=row.name, price_monthly=row.price_monthly, features=__import__('json').loads(row.features_json), is_active=row.is_active) for row in list_subscription_plans(db)]
    return SubscriptionPlansResponse(rows=rows)


@app.post('/billing/subscribe', response_model=SubscriptionCheckoutResponse)
def billing_subscribe_endpoint(req: SubscriptionCheckoutRequest, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> SubscriptionCheckoutResponse:
    try:
        if req.provider == 'stripe':
            sub, checkout_url = create_stripe_checkout(db, session.user, plan_code=req.plan_code)
        else:
            sub = create_subscription_checkout(db, session.user, plan_code=req.plan_code, provider=req.provider)
            checkout_url = f'/billing/mock/checkout/{sub.id}'
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SubscriptionCheckoutResponse(subscription_id=sub.id, plan_code=sub.plan_code, status=sub.status, provider=sub.provider, checkout_url=checkout_url)


@app.post('/billing/mock/checkout/{subscription_id}/complete', response_model=UserSubscriptionResponse)
def billing_mock_complete_endpoint(subscription_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> UserSubscriptionResponse:
    sub = activate_subscription_checkout(db, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail='Subscription not found')
    return _billing_to_response(sub)


@app.get('/billing/me', response_model=UserSubscriptionResponse | None)
def billing_me_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)):
    sub = get_active_subscription(db, session.user)
    if not sub:
        return None
    return _billing_to_response(sub)


@app.post('/billing/cancel', response_model=UserSubscriptionResponse)
def billing_cancel_endpoint(req: SubscriptionCancelRequest, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> UserSubscriptionResponse:
    sub = cancel_user_subscription(db, session.user, immediate=req.immediate)
    if not sub:
        raise HTTPException(status_code=404, detail='Subscription not found')
    return _billing_to_response(sub)


@app.post('/billing/resume', response_model=UserSubscriptionResponse)
def billing_resume_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> UserSubscriptionResponse:
    sub = resume_user_subscription(db, session.user)
    if not sub:
        raise HTTPException(status_code=404, detail='Subscription not found or cannot be resumed')
    return _billing_to_response(sub)


@app.post('/billing/portal', response_model=BillingPortalResponse)
def billing_portal_endpoint(req: BillingPortalRequest, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingPortalResponse:
    _sub, url = create_billing_portal_link(db, session.user, return_url=req.return_url)
    return BillingPortalResponse(url=url)


@app.get('/billing/account', response_model=BillingAccountResponse)
def billing_account_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingAccountResponse:
    payload = get_billing_account_summary(db, session.user)
    plans = [SubscriptionPlanResponse(code=row.code, name=row.name, price_monthly=row.price_monthly, features=__import__('json').loads(row.features_json), is_active=row.is_active) for row in payload['plans']]
    recent_events = [BillingEventRow(event_id=row.stripe_event_id, event_type=row.event_type, processed_at=row.processed_at) for row in payload['recent_billing_events']]
    return BillingAccountResponse(
        user=_user_to_response(session.user),
        entitlements=BillingEntitlementsResponse(**payload['entitlements']),
        subscription=(_billing_to_response(payload['subscription']) if payload['subscription'] else None),
        plans=plans,
        recent_billing_events=recent_events,
    )


@app.get('/billing/history', response_model=BillingHistoryResponse)
def billing_history_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingHistoryResponse:
    payload = get_billing_history(db, session.user)
    return BillingHistoryResponse(
        invoices=[BillingInvoiceRow(invoice_id=row.invoice_id, provider_invoice_id=row.provider_invoice_id, subscription_id=row.subscription_id, status=row.status, amount_paid=row.amount_paid, currency=row.currency, hosted_invoice_url=row.hosted_invoice_url, pdf_download_token=row.pdf_download_token, pdf_filename=row.pdf_filename, pdf_generated_at=row.pdf_generated_at, period_start=row.period_start, period_end=row.period_end, paid_at=row.paid_at, created_at=row.created_at) for row in payload['invoices']],
        recent_billing_events=[BillingEventRow(event_id=row.stripe_event_id, event_type=row.event_type, processed_at=row.processed_at) for row in payload['recent_billing_events']],
        email_notifications=[EmailNotificationRow(notification_id=row.id, to_email=row.to_email, template_key=row.template_key, event_type=row.event_type, subject=row.subject, provider=row.provider, provider_message_id=row.provider_message_id, status=row.status, error_message=None, created_at=row.created_at, sent_at=row.sent_at) for row in payload['email_notifications']],
    )


@app.get('/billing/invoices', response_model=BillingInvoicesResponse)
def billing_invoices_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingInvoicesResponse:
    rows = list_billing_invoices(db, user=session.user, limit=100)
    return BillingInvoicesResponse(rows=[BillingInvoiceRow(invoice_id=row.invoice_id, provider_invoice_id=row.provider_invoice_id, subscription_id=row.subscription_id, status=row.status, amount_paid=row.amount_paid, currency=row.currency, hosted_invoice_url=row.hosted_invoice_url, pdf_download_token=row.pdf_download_token, pdf_filename=row.pdf_filename, pdf_generated_at=row.pdf_generated_at, period_start=row.period_start, period_end=row.period_end, paid_at=row.paid_at, created_at=row.created_at) for row in rows])


@app.get('/billing/emails', response_model=EmailNotificationsResponse)
def billing_emails_endpoint(session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> EmailNotificationsResponse:
    rows = list_email_notifications(db, user=session.user, limit=100)
    return EmailNotificationsResponse(rows=[EmailNotificationRow(notification_id=row.id, to_email=row.to_email, template_key=row.template_key, event_type=row.event_type, subject=row.subject, provider=row.provider, provider_message_id=row.provider_message_id, status=row.status, error_message=None, created_at=row.created_at, sent_at=row.sent_at) for row in rows])


@app.get('/billing/invoices/{invoice_id}/links', response_model=BillingInvoiceLinksResponse)
def billing_invoice_links_endpoint(invoice_id: str, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> BillingInvoiceLinksResponse:
    row = get_billing_invoice_for_user(db, invoice_id, session.user)
    if not row:
        raise HTTPException(status_code=404, detail='Invoice not found')
    signed_url, expires_at = build_signed_invoice_url(row)
    return BillingInvoiceLinksResponse(invoice_id=row.invoice_id, hosted_invoice_url=row.hosted_invoice_url, pdf_download_url=build_invoice_download_url(row), signed_public_pdf_url=signed_url, expires_at=expires_at, pdf_filename=row.pdf_filename)


@app.get('/billing/invoices/{invoice_id}/public-link', response_model=SignedInvoiceLinkResponse)
def billing_invoice_public_link_endpoint(invoice_id: str, hours: int = 24, session: _db_models.UserSessionORM = Depends(require_user_session), db: Session = Depends(get_db)) -> SignedInvoiceLinkResponse:
    row = get_billing_invoice_for_user(db, invoice_id, session.user)
    if not row:
        raise HTTPException(status_code=404, detail='Invoice not found')
    signed_url, expires_at = build_signed_invoice_url(row, expires_at=(datetime.utcnow() + timedelta(hours=max(1, min(hours, 168)))))
    return SignedInvoiceLinkResponse(invoice_id=row.invoice_id, public_url=signed_url, expires_at=expires_at)


@app.get('/public/invoices/{invoice_id}')
def public_invoice_download_endpoint(invoice_id: str, token: str | None = None, expires: int | None = None, sig: str | None = None, db: Session = Depends(get_db)):
    row = db.scalar(select(_db_models.BillingInvoiceORM).where(_db_models.BillingInvoiceORM.invoice_id == invoice_id))
    if not row or not verify_signed_invoice_access(row, token=token, expires=expires, sig=sig):
        raise HTTPException(status_code=404, detail='Invoice not found')
    user = db.get(_db_models.UserORM, row.user_id) if row.user_id else None
    pdf_bytes = render_invoice_pdf(row, user=user)
    headers = {'Content-Disposition': f'inline; filename="{row.pdf_filename or (row.invoice_id + ".pdf")}"'}
    return Response(content=pdf_bytes, media_type='application/pdf', headers=headers)


@app.get('/billing/invoices/{invoice_id}/download')
def billing_invoice_download_endpoint(invoice_id: str, token: str | None = None, credentials = Depends(bearer), db: Session = Depends(get_db)):
    session = get_user_session(credentials, db) if credentials else None
    row = None
    if session is not None:
        row = get_billing_invoice_for_user(db, invoice_id, session.user)
    if row is None and token:
        row = db.scalar(select(_db_models.BillingInvoiceORM).where(_db_models.BillingInvoiceORM.invoice_id == invoice_id, _db_models.BillingInvoiceORM.pdf_download_token == token))
    if not row:
        raise HTTPException(status_code=404, detail='Invoice not found')
    user = db.get(_db_models.UserORM, row.user_id) if row.user_id else None
    pdf_bytes = render_invoice_pdf(row, user=user)
    headers = {'Content-Disposition': f'attachment; filename="{row.pdf_filename or (row.invoice_id + ".pdf")}"'}
    return Response(content=pdf_bytes, media_type='application/pdf', headers=headers)


@app.get('/affiliate/links', response_model=list[AffiliateLinkResponse])
def affiliate_links_endpoint(db: Session = Depends(get_db)) -> list[AffiliateLinkResponse]:
    return [AffiliateLinkResponse(bookmaker=row.bookmaker, base_url=row.base_url, affiliate_code=row.affiliate_code, campaign_code=row.campaign_code, is_active=row.is_active) for row in list_affiliate_links(db)]


@app.post('/affiliate/links', response_model=AffiliateLinkResponse)
def affiliate_upsert_endpoint(req: AffiliateLinkUpsertRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AffiliateLinkResponse:
    row = upsert_affiliate_link(db, bookmaker=req.bookmaker, base_url=req.base_url, affiliate_code=req.affiliate_code, campaign_code=req.campaign_code, is_active=req.is_active)
    return AffiliateLinkResponse(bookmaker=row.bookmaker, base_url=row.base_url, affiliate_code=row.affiliate_code, campaign_code=row.campaign_code, is_active=row.is_active)


@app.post('/affiliate/resolve', response_model=AffiliateResolveResponse)
def affiliate_resolve_endpoint(req: AffiliateResolveRequest, db: Session = Depends(get_db)) -> AffiliateResolveResponse:
    url, row, click = resolve_affiliate_url(db, bookmaker=req.bookmaker, capper_username=req.capper_username, ticket_id=req.ticket_id, source=req.source)
    return AffiliateResolveResponse(bookmaker=req.bookmaker.lower(), resolved_url=url, campaign_code=(row.campaign_code if row else None), click_token=click.click_token)




@app.post('/affiliate/conversions', response_model=AffiliateConversionRow)
def affiliate_conversion_record_endpoint(req: AffiliateConversionRecordRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AffiliateConversionRow:
    row = record_affiliate_conversion(db, click_token=req.click_token, bookmaker=req.bookmaker, revenue_amount=req.revenue_amount, currency=req.currency, external_ref=req.external_ref, metadata=req.metadata)
    return AffiliateConversionRow(conversion_id=row.id, click_token=row.click_token, bookmaker=row.bookmaker, revenue_amount=row.revenue_amount, currency=row.currency, external_ref=row.external_ref, created_at=row.created_at)


@app.get('/affiliate/conversions', response_model=AffiliateConversionsResponse)
def affiliate_conversions_endpoint(bookmaker: str | None = None, db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('tracked_cappers'))) -> AffiliateConversionsResponse:
    rows = list_affiliate_conversions(db, bookmaker=bookmaker, limit=100)
    return AffiliateConversionsResponse(rows=[AffiliateConversionRow(conversion_id=row.id, click_token=row.click_token, bookmaker=row.bookmaker, revenue_amount=row.revenue_amount, currency=row.currency, external_ref=row.external_ref, created_at=row.created_at) for row in rows])


@app.post('/affiliate/postback', response_model=AffiliateWebhookEventRow)
def affiliate_postback_endpoint(req: AffiliatePostbackRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AffiliateWebhookEventRow:
    event, _conversion = ingest_affiliate_postback(db, source_type='postback', click_token=req.click_token, bookmaker=req.bookmaker, revenue_amount=req.revenue_amount, currency=req.currency, external_ref=req.external_ref, metadata=req.metadata)
    return AffiliateWebhookEventRow(event_id=event.id, source_type=event.source_type, network=event.network, external_ref=event.external_ref, click_token=event.click_token, status=event.status, conversion_id=event.conversion_id, payload_summary=((event.payload_json or '')[:120] if getattr(event, 'payload_json', None) else None), created_at=event.created_at)


@app.post('/affiliate/webhooks/{network}', response_model=AffiliateWebhookEventRow)
def affiliate_webhook_endpoint(network: str, req: AffiliateWebhookIngestRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AffiliateWebhookEventRow:
    payload = req.payload or {}
    click_token = req.click_token or payload.get('click_token') or payload.get('subid') or payload.get('click_id') or payload.get('clickId')
    bookmaker = req.bookmaker or payload.get('bookmaker') or payload.get('brand')
    revenue_amount = req.revenue_amount if req.revenue_amount is not None else payload.get('revenue_amount') or payload.get('payout')
    external_ref = req.external_ref or payload.get('external_ref') or payload.get('conversion_id') or payload.get('event_id')
    event, _conversion = ingest_affiliate_postback(db, source_type='webhook', network=network, click_token=click_token, bookmaker=bookmaker, revenue_amount=(float(revenue_amount) if revenue_amount is not None else None), currency=req.currency, external_ref=(str(external_ref) if external_ref is not None else None), metadata=payload)
    return AffiliateWebhookEventRow(event_id=event.id, source_type=event.source_type, network=event.network, external_ref=event.external_ref, click_token=event.click_token, status=event.status, conversion_id=event.conversion_id, payload_summary=((event.payload_json or '')[:120] if getattr(event, 'payload_json', None) else None), created_at=event.created_at)


@app.get('/affiliate/webhooks', response_model=AffiliateWebhookEventsResponse)
def affiliate_webhooks_endpoint(db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('tracked_cappers'))) -> AffiliateWebhookEventsResponse:
    rows = list_affiliate_webhook_events(db, limit=100)
    return AffiliateWebhookEventsResponse(rows=[AffiliateWebhookEventRow(event_id=row.id, source_type=row.source_type, network=row.network, external_ref=row.external_ref, click_token=row.click_token, status=row.status, conversion_id=row.conversion_id, created_at=row.created_at) for row in rows])

@app.get('/affiliate/analytics', response_model=AffiliateAnalyticsResponse)
def affiliate_analytics_endpoint(db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('tracked_cappers'))) -> AffiliateAnalyticsResponse:
    return AffiliateAnalyticsResponse(rows=[AffiliateAnalyticsRow(**row) for row in affiliate_analytics(db)])


@app.get('/affiliate/analytics/{bookmaker}', response_model=AffiliateAnalyticsResponse)
def affiliate_analytics_bookmaker_endpoint(bookmaker: str, db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('tracked_cappers'))) -> AffiliateAnalyticsResponse:
    return AffiliateAnalyticsResponse(rows=[AffiliateAnalyticsRow(**row) for row in affiliate_analytics(db, bookmaker=bookmaker)])


@app.post('/admin/cappers/{username}/verify', response_model=CapperVerificationResponse)
def capper_verify_endpoint(username: str, req: CapperVerificationRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> CapperVerificationResponse:
    row = set_capper_verification(db, username=username, verified=True, badge=req.badge, note=req.note)
    return CapperVerificationResponse(username=row.username, verified=row.is_verified, verification_badge=row.verification_badge, verification_note=row.verification_note)


@app.post('/admin/cappers/{username}/unverify', response_model=CapperVerificationResponse)
def capper_unverify_endpoint(username: str, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> CapperVerificationResponse:
    row = set_capper_verification(db, username=username, verified=False)
    return CapperVerificationResponse(username=row.username, verified=row.is_verified, verification_badge=row.verification_badge, verification_note=row.verification_note)


@app.post('/parse', response_model=ParseResponse)
def parse_endpoint(req: ParseRequest) -> ParseResponse:
    return ParseResponse(legs=parse_text(req.text, sport_hint=req.sport_hint))


@app.post('/odds/match', response_model=OddsMatchResponse)
def odds_match_endpoint(req: OddsMatchRequest) -> OddsMatchResponse:
    return match_ticket_odds(req.text, bookmaker=req.bookmaker, posted_at=req.posted_at)


@app.get('/public/cappers/{username}', response_model=PublicCapperProfileResponse)
def public_capper_profile_endpoint(username: str, db: Session = Depends(get_db)) -> PublicCapperProfileResponse:
    normalized = username.lower().lstrip('@').strip()
    profile = get_or_create_capper_profile(db, normalized)
    if not profile.is_public:
        raise HTTPException(status_code=404, detail='Capper not found')
    summary_rows = compute_capper_dashboard(db, normalized, public_only=True)
    roi_rows = compute_capper_roi_dashboard(db, normalized, public_only=True)
    if not summary_rows:
        summary_rows = [{
            'username': normalized,
            'total_tickets': 0,
            'unique_tickets': 0,
            'duplicate_tickets': 0,
            'cashed': 0,
            'lost': 0,
            'pending': 0,
            'needs_review': 0,
            'settled_tickets': 0,
            'hit_rate': 0.0,
        }]
    stmt = select(_db_models.TicketORM).where(_db_models.TicketORM.source_type == 'tweet', _db_models.TicketORM.duplicate_of_ticket_id.is_(None), _db_models.TicketORM.is_hidden == False, func.lower(_db_models.TicketORM.source_ref).like(f'%/{normalized}/status/%')).order_by(_db_models.TicketORM.created_at.desc(), _db_models.TicketORM.id.desc()).limit(10)
    tickets = list(db.scalars(stmt).all())
    return PublicCapperProfileResponse(username=normalized, verified=profile.is_verified, verification_badge=profile.verification_badge, summary=CapperDashboardRow(**summary_rows[0]), roi_summary=CapperRoiDashboardRow(**roi_rows[0]) if roi_rows else None, recent_tickets=[ticket_to_response(t) for t in tickets])




@app.get('/public/leaderboard', response_model=PublicLeaderboardResponse)
def public_leaderboard_endpoint(db: Session = Depends(get_db)) -> PublicLeaderboardResponse:
    dashboard_rows = {row['username']: row for row in compute_capper_dashboard(db, public_only=True)}
    roi_rows = {row['username']: row for row in compute_capper_roi_dashboard(db, public_only=True)}
    rows: list[PublicLeaderboardRow] = []
    for username, summary in dashboard_rows.items():
        rows.append(PublicLeaderboardRow(
            username=username,
            hit_rate=summary['hit_rate'],
            roi=roi_rows.get(username, {}).get('roi'),
            settled_tickets=summary['settled_tickets'],
        ))
    rows.sort(key=lambda r: (-(r.roi if r.roi is not None else -9999), -r.hit_rate, -r.settled_tickets, r.username))
    return PublicLeaderboardResponse(rows=rows)


@app.get('/leaderboard', response_class=HTMLResponse)
def leaderboard_page(db: Session = Depends(get_db)) -> HTMLResponse:
    payload = public_leaderboard_endpoint(db)
    rows = ''.join(f"<tr><td><a href='/cappers/{row.username}'>{row.username}</a></td><td>{row.hit_rate:.1%}</td><td>{'' if row.roi is None else f'{row.roi:.1%}'}</td><td>{row.settled_tickets}</td></tr>" for row in payload.rows) or '<tr><td colspan=4>No public cappers yet</td></tr>'
    html = f"""<!doctype html><html><head><title>ParlayBot Leaderboard</title><style>body{{font-family:Arial,Helvetica,sans-serif;margin:40px;}}table{{border-collapse:collapse;width:100%;max-width:900px;}}th,td{{border:1px solid #ddd;padding:10px;text-align:left;}}th{{background:#f5f5f5;}}a{{color:#0a58ca;text-decoration:none;}}</style></head><body><h1>Public Capper Leaderboard</h1><p>Step 11 frontend page.</p><table><thead><tr><th>Capper</th><th>Hit Rate</th><th>ROI</th><th>Settled Tickets</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    return HTMLResponse(html)


@app.get('/cappers/{username}', response_class=HTMLResponse)
def capper_profile_page(username: str, db: Session = Depends(get_db)) -> HTMLResponse:
    profile = public_capper_profile_endpoint(username, db)
    tickets = ''.join(f"<li>{t.overall.upper()} — {t.raw_text.replace(chr(10), ' / ')}</li>" for t in profile.recent_tickets) or '<li>No recent public tickets</li>'
    roi_text = 'N/A' if profile.roi_summary is None else f"{profile.roi_summary.roi:.1%} ROI on {profile.roi_summary.settled_with_stake} tracked slips"
    html = f"""<!doctype html><html><head><title>@{profile.username}</title><style>body{{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:900px;}}a{{color:#0a58ca;text-decoration:none;}}.card{{border:1px solid #ddd;border-radius:10px;padding:20px;}}</style></head><body><p><a href='/leaderboard'>← Back to leaderboard</a></p><div class='card'><h1>@{profile.username}</h1><p>Hit rate: {profile.summary.hit_rate:.1%} across {profile.summary.settled_tickets} settled public tickets.</p><p>{roi_text}</p><h2>Recent tickets</h2><ul>{tickets}</ul></div></body></html>"""
    return HTMLResponse(html)


@app.get('/admin/auth/status', response_model=AdminAuthStatusResponse)
def admin_auth_status(_: str = Depends(require_admin)) -> AdminAuthStatusResponse:
    return AdminAuthStatusResponse(authenticated=True)


@app.get('/admin/moderation/tickets/hidden', response_model=list[TicketDetailResponse])
def hidden_tickets_endpoint(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> list[TicketDetailResponse]:
    return [ticket_to_response(t) for t in list_hidden_tickets(db)]


@app.post('/admin/moderation/tickets/{ticket_id}/hide', response_model=TicketDetailResponse)
def hide_ticket_endpoint(ticket_id: str, req: ModerationRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> TicketDetailResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')
    hide_ticket(db, ticket, req.reason)
    ticket = get_ticket(db, ticket_id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/admin/moderation/tickets/{ticket_id}/unhide', response_model=TicketDetailResponse)
def unhide_ticket_endpoint(ticket_id: str, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> TicketDetailResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')
    unhide_ticket(db, ticket)
    ticket = get_ticket(db, ticket_id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/admin/moderation/cappers/{username}/hide-profile', response_model=CapperModerationResponse)
def hide_capper_profile_endpoint(username: str, req: ModerationRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> CapperModerationResponse:
    row = set_capper_profile_visibility(db, username, is_public=False, moderation_note=req.reason)
    return CapperModerationResponse(username=row.username, is_public=row.is_public, moderation_note=row.moderation_note)


@app.post('/admin/moderation/cappers/{username}/show-profile', response_model=CapperModerationResponse)
def show_capper_profile_endpoint(username: str, req: ModerationRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> CapperModerationResponse:
    row = set_capper_profile_visibility(db, username, is_public=True, moderation_note=req.reason)
    return CapperModerationResponse(username=row.username, is_public=row.is_public, moderation_note=row.moderation_note)


@app.get('/admin/cappers', response_model=list[AdminCapperProfileResponse])
def admin_cappers_list_endpoint(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> list[AdminCapperProfileResponse]:
    return [_capper_admin_profile_to_response(row) for row in list_capper_profiles(db)]


@app.get('/admin/cappers/{username}', response_model=AdminCapperProfileResponse)
def admin_cappers_get_endpoint(username: str, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AdminCapperProfileResponse:
    row = get_capper_profile(db, username)
    if not row:
        raise HTTPException(status_code=404, detail='Capper profile not found')
    return _capper_admin_profile_to_response(row)


@app.post('/admin/cappers', response_model=AdminCapperProfileResponse)
def admin_cappers_create_endpoint(req: AdminCapperCreateRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AdminCapperProfileResponse:
    try:
        row = create_capper_profile(db, req.username, display_name=req.display_name, bio=req.bio, is_public=req.is_public, moderation_note=req.moderation_note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _capper_admin_profile_to_response(row)


@app.patch('/admin/cappers/{username}', response_model=AdminCapperProfileResponse)
def admin_cappers_update_endpoint(username: str, req: AdminCapperUpdateRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AdminCapperProfileResponse:
    row = update_capper_profile_admin(db, username, display_name=req.display_name, bio=req.bio, is_public=req.is_public, moderation_note=req.moderation_note)
    return _capper_admin_profile_to_response(row)


@app.post('/admin/cappers/{username}/deactivate', response_model=AdminCapperProfileResponse)
def admin_cappers_deactivate_endpoint(username: str, req: ModerationRequest, db: Session = Depends(get_db), _: str = Depends(require_admin)) -> AdminCapperProfileResponse:
    row = update_capper_profile_admin(db, username, is_public=False, moderation_note=req.reason)
    return _capper_admin_profile_to_response(row)

@app.post('/slips/parse', response_model=SlipParseResponse)
def parse_slip_endpoint(req: SlipParseRequest) -> SlipParseResponse:
    parsed = parse_slip_text(req.text, bookmaker_hint=req.bookmaker_hint)
    financials = extract_financials(req.text, bookmaker_hint=parsed.bookmaker)
    return SlipParseResponse(bookmaker=parsed.bookmaker, cleaned_text=parsed.cleaned_text, notes=parsed.notes + (financials.notes or []), stake_amount=financials.stake_amount, to_win_amount=financials.to_win_amount, american_odds=financials.american_odds, decimal_odds=financials.decimal_odds)


@app.get('/slips/templates', response_model=list[SlipTemplateResponse])
def slip_templates_endpoint() -> list[SlipTemplateResponse]:
    return [
        SlipTemplateResponse(
            bookmaker='draftkings',
            title='DraftKings parlay paste template',
            template_text='''NBA SGP\nNikola Jokic 25+ Points\nJamal Murray Over 1.5 Threes\nDenver Nuggets Moneyline\nOdds +240\nStake 25\nTo Win 60''',
            notes=['Best for OCR cleanup and manual review entry', 'Include stake and odds if available'],
        ),
        SlipTemplateResponse(
            bookmaker='fanduel',
            title='FanDuel parlay paste template',
            template_text='''Same Game Parlay\nJayson Tatum Over 24.5 Points\nBoston Celtics ML\nGame Total Under 232.5\nAmerican Odds +310\nRisk 20\nPayout 82''',
            notes=['Use full player names when possible', 'Risk = stake, payout includes stake on some slips'],
        ),
        SlipTemplateResponse(
            bookmaker='bet365',
            title='bet365 bet slip template',
            template_text='''Bet Builder\nLeBron James Over 24.5 Points\nLakers Money Line\nOver 228.5 Total Points\nOdds 4.10\nStake 10''',
            notes=['Decimal odds are common on bet365', 'Current MVP now converts decimal odds to American odds and stores both'],
        ),
        SlipTemplateResponse(
            bookmaker='generic',
            title='Generic text template',
            template_text='''Denver ML\nJokic 25+ pts\nMurray over 1.5 threes\nStake 25\nOdds +240''',
            notes=['Fastest format for the parser today'],
        ),
    ]


@app.post('/grade', response_model=GradeResponse)
def grade_endpoint(req: GradeRequest) -> GradeResponse:
    try:
        parsed_bet_date = date.fromisoformat(req.bet_date) if req.bet_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='bet_date must be YYYY-MM-DD') from exc
    return grade_text(req.text, posted_at=req.posted_at, bet_date=parsed_bet_date)


@app.post('/tickets/grade-and-save', response_model=TicketDetailResponse)
def grade_and_save_endpoint(req: GradeRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    try:
        parsed_bet_date = date.fromisoformat(req.bet_date) if req.bet_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='bet_date must be YYYY-MM-DD') from exc
    result = grade_text(req.text, posted_at=req.posted_at, bet_date=parsed_bet_date)
    ticket = save_graded_ticket(db, req.text, result, posted_at=req.posted_at)
    enqueue_review_if_needed(db, ticket, result)
    ticket = get_ticket(db, ticket.id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.get('/tickets/{ticket_id}', response_model=TicketDetailResponse)
def get_ticket_endpoint(ticket_id: str, db: Session = Depends(get_db)) -> TicketDetailResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')
    return ticket_to_response(ticket)


@app.post('/tickets/{ticket_id}/financials', response_model=TicketDetailResponse)
def update_ticket_financials_endpoint(ticket_id: str, req: TicketFinancialsUpdateRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')
    update_ticket_financials(
        db,
        ticket,
        stake_amount=req.stake_amount,
        to_win_amount=req.to_win_amount,
        american_odds=req.american_odds,
        decimal_odds=req.decimal_odds,
        bookmaker=req.bookmaker,
    )
    ticket = get_ticket(db, ticket_id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/tickets/{ticket_id}/manual-regrade', response_model=TicketDetailResponse)
def manual_regrade_endpoint(ticket_id: str, req: ManualTicketRegradeRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail='Ticket not found')

    provider = get_results_provider()
    leg_map = {edit.leg_index: edit for edit in req.legs}
    graded_legs = []
    for idx, existing in enumerate(ticket.legs):
        leg = ticket_to_response(ticket).result.legs[idx].leg
        edit = leg_map.get(idx)
        if edit:
            data = leg.model_dump()
            for key, value in edit.model_dump(exclude_none=True).items():
                if key == 'leg_index':
                    continue
                data[key] = value
            leg = type(leg)(**data)
        graded_legs.append(settle_leg(leg, provider))

    if req.financials is not None:
        update_ticket_financials(
            db,
            ticket,
            stake_amount=req.financials.stake_amount,
            to_win_amount=req.financials.to_win_amount,
            american_odds=req.financials.american_odds,
            decimal_odds=req.financials.decimal_odds,
            bookmaker=req.financials.bookmaker,
        )
        ticket = get_ticket(db, ticket_id)
        assert ticket is not None

    manual_regrade_ticket(db, ticket, graded_legs, posted_at=req.posted_at, resolution_note=req.resolution_note)
    if req.resolve_review_id is not None:
        resolve_review_item(db, req.resolve_review_id, status='approved', resolution_note=req.resolution_note or 'Manual regrade applied')
    ticket = get_ticket(db, ticket_id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/ingest/tweet/grade', response_model=IngestGradeResponse)
def ingest_tweet_grade(req: TweetIngestRequest) -> IngestGradeResponse:
    normalized = normalize_tweet_payload(req.model_dump(exclude_none=True))
    financials = extract_financials(normalized['raw_text'])
    result = grade_text(normalized['cleaned_text'], posted_at=req.posted_at)
    return IngestGradeResponse(
        source_type='tweet',
        source_ref=normalized['source_ref'],
        extracted_text=normalized['raw_text'],
        cleaned_text=normalized['cleaned_text'],
        posted_at=req.posted_at,
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
        result=result,
    )


@app.post('/ingest/tweet/grade-and-save', response_model=TicketDetailResponse)
def ingest_tweet_grade_and_save(req: TweetIngestRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    normalized = normalize_tweet_payload(req.model_dump(exclude_none=True))
    financials = extract_financials(normalized['raw_text'])
    result = grade_text(normalized['cleaned_text'], posted_at=req.posted_at)
    ticket = save_graded_ticket(
        db,
        normalized['cleaned_text'],
        result,
        posted_at=req.posted_at,
        source_type='tweet',
        source_ref=normalized['source_ref'],
        source_payload_json=dump_source_payload(normalized['raw_payload']),
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
    )
    enqueue_review_if_needed(db, ticket, result)
    ticket = get_ticket(db, ticket.id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/ingest/x/fetch-and-grade', response_model=IngestGradeResponse)
def ingest_x_fetch_and_grade(req: XFetchRequest) -> IngestGradeResponse:
    x_client = get_x_client()
    tweet = x_client.fetch_tweet(req.tweet_id)
    payload = tweet.to_ingest_payload()
    if req.posted_at and not payload.get('posted_at'):
        payload['posted_at'] = req.posted_at
    normalized = normalize_tweet_payload(payload)
    effective_posted_at = payload.get('posted_at')
    financials = extract_financials(normalized['raw_text'])
    result = grade_text(normalized['cleaned_text'], posted_at=effective_posted_at)
    return IngestGradeResponse(
        source_type='tweet',
        source_ref=normalized['source_ref'],
        extracted_text=normalized['raw_text'],
        cleaned_text=normalized['cleaned_text'],
        posted_at=effective_posted_at,
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
        result=result,
    )


@app.post('/ingest/x/fetch-grade-and-save', response_model=TicketDetailResponse)
def ingest_x_fetch_grade_and_save(req: XFetchRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    x_client = get_x_client()
    tweet = x_client.fetch_tweet(req.tweet_id)
    payload = tweet.to_ingest_payload()
    if req.posted_at and not payload.get('posted_at'):
        payload['posted_at'] = req.posted_at
    normalized = normalize_tweet_payload(payload)
    effective_posted_at = payload.get('posted_at')
    financials = extract_financials(normalized['raw_text'])
    result = grade_text(normalized['cleaned_text'], posted_at=effective_posted_at)
    ticket = save_graded_ticket(
        db,
        normalized['cleaned_text'],
        result,
        posted_at=effective_posted_at,
        source_type='tweet',
        source_ref=normalized['source_ref'],
        source_payload_json=dump_source_payload(tweet.raw_payload or payload),
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
    )
    enqueue_review_if_needed(db, ticket, result)
    ticket = get_ticket(db, ticket.id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.post('/ingest/x/webhook/grade-and-save', response_model=TicketDetailResponse)
def ingest_x_webhook_grade_and_save(req: TweetIngestRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    return ingest_tweet_grade_and_save(req, db)


@app.post('/ingest/screenshot/ocr', response_model=OCRExtractResponse)
async def ingest_screenshot_ocr(file: UploadFile = File(...)) -> OCRExtractResponse:
    content = await file.read()
    try:
        validate_image_upload(file.filename or 'upload', content)
        ocr = get_ocr_provider()
        result = ocr.extract_text(file.filename or 'upload', content)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OCRExtractResponse(
        filename=file.filename or 'upload',
        raw_text=result.raw_text,
        cleaned_text=result.cleaned_text,
        provider=result.provider,
        confidence=result.confidence,
        notes=result.notes,
    )


@app.post('/ingest/screenshot/grade', response_model=IngestGradeResponse)
async def ingest_screenshot_grade(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    posted_at: str | None = Form(default=None),
    bookmaker_hint: str | None = Form(default=None),
    bet_date: str | None = Form(default=None),
) -> IngestGradeResponse:
    _enforce_public_check_rate_limit(request, response, 'screenshot-grade')
    content = await file.read()
    try:
        validate_image_upload(file.filename or 'upload', content)
        ocr = get_ocr_provider()
        ocr_result = ocr.extract_text(file.filename or 'upload', content)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_posted_at = datetime.fromisoformat(posted_at) if posted_at else None
    parsed_slip = parse_slip_text(ocr_result.cleaned_text, bookmaker_hint=bookmaker_hint)
    parsed_screenshot = parse_screenshot_text(ocr_result.raw_text, parsed_slip.cleaned_text)
    financials = extract_financials(ocr_result.raw_text, bookmaker_hint=parsed_slip.bookmaker)
    parsed_bet_date = date.fromisoformat(bet_date) if bet_date else (date.fromisoformat(parsed_screenshot.detected_bet_date) if parsed_screenshot.detected_bet_date else None)
    grading_text = '\n'.join(leg.normalized_label for leg in parsed_screenshot.parsed_legs) or parsed_slip.cleaned_text
    result = grade_text(grading_text, posted_at=parsed_posted_at, bet_date=parsed_bet_date)
    return IngestGradeResponse(
        source_type='screenshot',
        source_ref=file.filename or 'upload',
        extracted_text=ocr_result.raw_text,
        cleaned_text=grading_text,
        posted_at=parsed_posted_at,
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
        parsed_screenshot=parsed_screenshot,
        result=result,
    )


@app.post('/ingest/screenshot/grade-and-save', response_model=TicketDetailResponse)
async def ingest_screenshot_grade_and_save(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    posted_at: str | None = Form(default=None),
    bookmaker_hint: str | None = Form(default=None),
    bet_date: str | None = Form(default=None),
) -> TicketDetailResponse:
    content = await file.read()
    try:
        validate_image_upload(file.filename or 'upload', content)
        ocr = get_ocr_provider()
        ocr_result = ocr.extract_text(file.filename or 'upload', content)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_posted_at = datetime.fromisoformat(posted_at) if posted_at else None
    parsed_slip = parse_slip_text(ocr_result.cleaned_text, bookmaker_hint=bookmaker_hint)
    parsed_screenshot = parse_screenshot_text(ocr_result.raw_text, parsed_slip.cleaned_text)
    financials = extract_financials(ocr_result.raw_text, bookmaker_hint=parsed_slip.bookmaker)
    parsed_bet_date = date.fromisoformat(bet_date) if bet_date else (date.fromisoformat(parsed_screenshot.detected_bet_date) if parsed_screenshot.detected_bet_date else None)
    grading_text = '\n'.join(leg.normalized_label for leg in parsed_screenshot.parsed_legs) or parsed_slip.cleaned_text
    result = grade_text(grading_text, posted_at=parsed_posted_at, bet_date=parsed_bet_date)
    ticket = save_graded_ticket(
        db,
        grading_text,
        result,
        posted_at=parsed_posted_at,
        source_type='screenshot',
        source_ref=file.filename or 'upload',
        source_payload_json=dump_source_payload({
            'ocr_provider': ocr_result.provider,
            'ocr_confidence': ocr_result.confidence,
            'ocr_notes': ocr_result.notes,
            'raw_text': ocr_result.raw_text,
            'bookmaker': parsed_slip.bookmaker,
            'bookmaker_notes': parsed_slip.notes,
            'financial_notes': financials.notes,
            'parsed_screenshot': parsed_screenshot.model_dump(),
        }),
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
    )
    enqueue_review_if_needed(db, ticket, result, ocr_confidence=ocr_result.confidence)
    ticket = get_ticket(db, ticket.id)
    assert ticket is not None
    return ticket_to_response(ticket)


@app.get('/review-queue', response_model=list[ReviewQueueItemResponse])
def review_queue_list(status: str = 'open', db: Session = Depends(get_db)) -> list[ReviewQueueItemResponse]:
    return [review_item_to_response(item) for item in list_review_items(db, status=status)]


@app.post('/review-queue/{review_id}/resolve', response_model=ReviewQueueItemResponse)
def review_queue_resolve(review_id: int, req: ReviewResolveRequest, db: Session = Depends(get_db)) -> ReviewQueueItemResponse:
    item = resolve_review_item(db, review_id, status=req.status, resolution_note=req.resolution_note)
    if not item:
        raise HTTPException(status_code=404, detail='Review item not found')
    return review_item_to_response(item)


@app.get('/admin/aliases', response_model=list[AliasResponse])
def aliases_list(alias_type: str | None = None, db: Session = Depends(get_db)) -> list[AliasResponse]:
    return [alias_to_response(item) for item in list_aliases(db, alias_type=alias_type)]


@app.post('/admin/aliases', response_model=AliasResponse)
def aliases_upsert(req: AliasUpsertRequest, db: Session = Depends(get_db)) -> AliasResponse:
    row = upsert_alias(db, req.alias_type, req.alias, req.canonical_value, created_by=req.created_by)
    load_alias_overrides(db)
    return alias_to_response(row)


@app.get('/watch-accounts', response_model=list[WatchAccountResponse])
def watch_accounts_list(db: Session = Depends(get_db)) -> list[WatchAccountResponse]:
    return [watched_account_to_response(item) for item in list_watched_accounts(db)]


@app.post('/watch-accounts', response_model=WatchAccountResponse)
def watch_accounts_upsert(req: WatchAccountRequest, db: Session = Depends(get_db)) -> WatchAccountResponse:
    row = upsert_watched_account(db, req.username, req.poll_interval_minutes, req.is_enabled)
    return watched_account_to_response(row)


@app.post('/watch-accounts/{watch_id}/poll', response_model=PollRunResponse)
def watch_account_poll(watch_id: int, req: PollAccountRequest, db: Session = Depends(get_db)) -> PollRunResponse:
    account = db.get(_db_models.WatchedAccountORM, watch_id)
    if not account:
        raise HTTPException(status_code=404, detail='Watched account not found')
    x_client = get_x_client()
    run = poll_account_once(db, account, x_client=x_client, max_tweets=req.max_tweets)
    return poll_run_to_response(run)


@app.get('/poll-runs', response_model=list[PollRunResponse])
def poll_runs_list(limit: int = 25, db: Session = Depends(get_db)) -> list[PollRunResponse]:
    return [poll_run_to_response(item) for item in list_poll_runs(db, limit=limit)]


@app.get('/tickets/dedupe/check', response_model=TicketDeduplicationResponse)
def check_ticket_duplicate(text: str, posted_at: datetime | None = None, source_type: str | None = None, source_ref: str | None = None, db: Session = Depends(get_db)) -> TicketDeduplicationResponse:
    duplicate = find_duplicate_ticket(db, text, posted_at=posted_at, source_type=source_type, source_ref=source_ref)
    dedupe_key = None
    if duplicate:
        dedupe_key = duplicate.dedupe_key
    else:
        from .services.repository import build_dedupe_key
        dedupe_key = build_dedupe_key(text, posted_at=posted_at, source_type=source_type, source_ref=source_ref)
    return TicketDeduplicationResponse(is_duplicate=duplicate is not None, duplicate_of_ticket_id=duplicate.id if duplicate else None, dedupe_key=dedupe_key)


@app.get('/scheduler/status', response_model=SchedulerStatusResponse)
def scheduler_status() -> SchedulerStatusResponse:
    cfg = get_scheduler_config()
    return SchedulerStatusResponse(enabled=cfg.enabled, interval_seconds=cfg.interval_seconds)


@app.post('/scheduler/run-due', response_model=SchedulerRunResponse)
def scheduler_run_due() -> SchedulerRunResponse:
    runs = run_due_polls_once()
    return SchedulerRunResponse(triggered_accounts=len(runs), created_runs=len(runs))


@app.get('/dashboard/cappers', response_model=CapperDashboardResponse)
def capper_dashboard(db: Session = Depends(get_db)) -> CapperDashboardResponse:
    rows = [CapperDashboardRow(**row) for row in compute_capper_dashboard(db)]
    return CapperDashboardResponse(rows=rows)


@app.get('/dashboard/cappers/{username}', response_model=CapperDashboardResponse)
def capper_dashboard_single(username: str, db: Session = Depends(get_db)) -> CapperDashboardResponse:
    rows = [CapperDashboardRow(**row) for row in compute_capper_dashboard(db, username=username)]
    return CapperDashboardResponse(rows=rows)


@app.get('/dashboard/cappers-roi', response_model=CapperRoiDashboardResponse)
def capper_roi_dashboard(db: Session = Depends(get_db)) -> CapperRoiDashboardResponse:
    rows = [CapperRoiDashboardRow(**row) for row in compute_capper_roi_dashboard(db)]
    return CapperRoiDashboardResponse(rows=rows)


@app.get('/dashboard/cappers-roi/{username}', response_model=CapperRoiDashboardResponse)
def capper_roi_dashboard_single(username: str, db: Session = Depends(get_db)) -> CapperRoiDashboardResponse:
    rows = [CapperRoiDashboardRow(**row) for row in compute_capper_roi_dashboard(db, username=username)]
    return CapperRoiDashboardResponse(rows=rows)


@app.get('/pro/review-queue', response_model=list[ReviewQueueItemResponse])
def pro_review_queue_list(status: str = 'open', db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('review_queue'))) -> list[ReviewQueueItemResponse]:
    return [review_item_to_response(item) for item in list_review_items(db, status=status)]


@app.get('/pro/dashboard/cappers-roi', response_model=CapperRoiDashboardResponse)
def pro_capper_roi_dashboard(db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('roi_dashboard'))) -> CapperRoiDashboardResponse:
    rows = [CapperRoiDashboardRow(**row) for row in compute_capper_roi_dashboard(db)]
    return CapperRoiDashboardResponse(rows=rows)


@app.get('/pro/dashboard/cappers-roi/{username}', response_model=CapperRoiDashboardResponse)
def pro_capper_roi_dashboard_single(username: str, db: Session = Depends(get_db), _: _db_models.UserSessionORM = Depends(require_entitlement('roi_dashboard'))) -> CapperRoiDashboardResponse:
    rows = [CapperRoiDashboardRow(**row) for row in compute_capper_roi_dashboard(db, username=username)]
    return CapperRoiDashboardResponse(rows=rows)
