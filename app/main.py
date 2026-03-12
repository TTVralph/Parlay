from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
import json
import logging
import os
import re
import threading
import time
from uuid import uuid4

from fastapi import Body, Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
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
from .services.slip_risk_analyzer import analyze_slip_risk
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
    GradedLeg,
    CheckJobCreateResponse,
    CheckJobStatusResponse,
    AnalyzeSlipResponse,
    IngestGradeResponse,
    OCRExtractResponse,
    ScreenshotParseResponse,
    VisionSanityDebugResponse,
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
from .parser import filter_valid_legs, parse_text
from .services.slip_parser import SlipParserService
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
    save_public_slip_result,
    get_public_slip_result,
    list_recent_public_slips,
)
from .providers.factory import get_results_provider
from .services.serializers import (
    alias_to_response,
    poll_run_to_response,
    review_item_to_response,
    ticket_to_response,
    watched_account_to_response,
)
from .services.debug_observability import debug_observability_enabled, get_debug_observability_service
from .services.snapshot_hydrator import SnapshotHydrator
from .x_client import get_x_client
from .services.vision_parser import OpenAIVisionSlipParser

app = FastAPI(title='Parlay Cash Checker MVP', version='1.9.0')
logger = logging.getLogger(__name__)
slip_parser_service = SlipParserService()
_VISION_SANITY_MODELS = {'gpt-4o-mini', 'gpt-4.1-mini'}


def _grade_text_with_observability(*args, **kwargs) -> GradeResponse:
    result = grade_text(*args, **kwargs)
    diagnostics = getattr(result, 'grading_diagnostics', None)
    if isinstance(diagnostics, dict):
        get_debug_observability_service().record_grading_diagnostics(diagnostics)
    return result


def _screenshot_parsed_to_grading_text(parsed_screenshot) -> str:
    return '\n'.join(leg.normalized_label for leg in parsed_screenshot.parsed_legs)




def _screenshot_parse_debug_enabled() -> bool:
    explicit = os.getenv('PARLAY_ENABLE_SCREENSHOT_PARSE_DEBUG', '').strip().lower()
    if explicit in {'1', 'true', 'yes', 'on'}:
        return True
    if explicit in {'0', 'false', 'no', 'off'}:
        return False
    environment = (
        os.getenv('PARLAY_ENV')
        or os.getenv('APP_ENV')
        or os.getenv('ENV')
        or os.getenv('FASTAPI_ENV')
        or ''
    ).strip().lower()
    return environment in {'dev', 'development', 'local', 'test', 'testing'}

def _parse_screenshot_with_vision(content: bytes, filename: str | None):
    parsed = slip_parser_service.parse(content, filename=filename)
    from .models import ParsedScreenshotLeg, ParsedScreenshotResponse, PrimaryParserDebug

    def _to_response(parsed_obj, *, include_primary: bool = True):
        parsed_legs = []
        for leg in parsed_obj.parsed_legs:
            normalized_label = leg.raw_text
            if leg.player_name and leg.selection and leg.line is not None and leg.market:
                normalized_label = f'{leg.player_name} {leg.selection.title()} {leg.line:g} {leg.market.title()}'
            parsed_legs.append(ParsedScreenshotLeg(
                raw_leg_text=leg.raw_text,
                raw_player_text=leg.raw_player_text or leg.player_name,
                player_name=leg.player_name,
                stat_type=leg.market,
                line=leg.line,
                direction=leg.selection,
                normalized_label=normalized_label,
                confidence=None,
                match_method=leg.match_method,
                match_confidence=leg.match_confidence,
            ))
        return ParsedScreenshotResponse(
            raw_text=parsed_obj.raw_text,
            parsed_legs=parsed_legs,
            detected_bet_date=parsed_obj.detected_bet_date,
            parse_warnings=parsed_obj.warnings,
            confidence=parsed_obj.confidence,
            preprocessing_metadata=parsed_obj.preprocessing_metadata,
            primary_parser_debug=PrimaryParserDebug(
                primary_parser_status=parsed_obj.primary_parser_status,
                primary_failure_category=parsed_obj.primary_failure_category,
                primary_provider_error=parsed_obj.primary_provider_error,
                primary_confidence=parsed_obj.primary_confidence,
                primary_warnings=parsed_obj.primary_warnings,
                primary_detected_sportsbook=parsed_obj.primary_detected_sportsbook,
                primary_parser_strategy_used=parsed_obj.primary_parser_strategy_used,
                primary_screenshot_state=parsed_obj.primary_screenshot_state,
                primary_parsed_leg_count=parsed_obj.primary_parsed_leg_count,
            ),
            primary_pre_fallback_result=_to_response(parsed_obj.primary_result, include_primary=False) if include_primary and parsed_obj.primary_result else None,
            fallback_reason=parsed_obj.fallback_reason,
            debug_artifacts=parsed_obj.debug_artifacts,
            parse_debug=getattr(parsed_obj, 'parse_debug', None) if _screenshot_parse_debug_enabled() else None,
        )

    return _to_response(parsed)
run_lightweight_migrations()


_public_check_rate_limit_lock = threading.Lock()
_public_check_rate_limit_hits: dict[str, list[float]] = {}
_public_check_jobs_lock = threading.Lock()
_public_check_jobs: dict[str, dict] = {}
_public_check_provider = ESPNNBAResultsProvider()
_PUBLIC_SLIP_ID_PATTERN = re.compile(r'^[a-z0-9]{8,16}$')


def _has_persistable_public_result(result: dict) -> bool:
    if not result.get('ok'):
        return False
    parsed_legs = [str(item).strip() for item in result.get('parsed_legs', []) if str(item).strip()]
    if not parsed_legs:
        return False
    legs = result.get('legs', [])
    if not isinstance(legs, list) or not legs:
        return False
    for leg in legs:
        if not isinstance(leg, dict):
            return False
        if not str(leg.get('leg', '')).strip():
            return False
    return True


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
    html = """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>ParlayBot</title>
  <style>
    :root{--bg:#070b14;--bg-soft:#0b1220;--surface:#111a2d;--surface-elev:#16223a;--border:#263954;--text:#f8fbff;--muted:#95a5c4;--primary:#3b82f6;--primary-2:#60a5fa;color-scheme:dark;}
    :root[data-theme='light']{--bg:#edf3ff;--bg-soft:#e2ebfb;--surface:#ffffff;--surface-elev:#f8fbff;--border:#cfddf1;--text:#0f172a;--muted:#475569;--primary:#2563eb;--primary-2:#1d4ed8;color-scheme:light;}
    *{box-sizing:border-box;}
    body{margin:0;font-family:Inter,system-ui,Arial,Helvetica,sans-serif;background:radial-gradient(1200px 600px at 5% -10%,#1d4ed833,transparent 65%),radial-gradient(1000px 600px at 95% -20%,#9333ea2e,transparent 62%),var(--bg);color:var(--text);}
    .shell{max-width:1080px;margin:0 auto;padding:28px 18px 44px;}
    .hero{border:1px solid var(--border);background:linear-gradient(160deg,var(--surface) 0%,var(--surface-elev) 60%,#1e3a8a26 100%);border-radius:26px;padding:28px;box-shadow:0 20px 60px #02061766;}
    .kicker{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;border:1px solid #60a5fa55;background:#60a5fa22;color:#bfdbfe;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;}
    h1{margin:16px 0 10px;font-size:clamp(32px,6vw,56px);line-height:1.02;letter-spacing:-.02em;max-width:14ch;}
    .hero-sub{margin:0;max-width:64ch;color:var(--muted);font-size:clamp(16px,2.2vw,20px);line-height:1.55;}
    .actions{margin-top:22px;display:flex;gap:12px;flex-wrap:wrap;}
    .btn{text-decoration:none;border-radius:14px;padding:13px 18px;font-weight:800;letter-spacing:.01em;display:inline-flex;align-items:center;justify-content:center;min-height:46px;}
    .btn-primary{background:linear-gradient(180deg,var(--primary),var(--primary-2));color:#fff;border:1px solid #1d4ed8;}
    .btn-secondary{border:1px solid var(--border);background:var(--bg-soft);color:var(--text);}
    .section-title{margin:28px 0 12px;font-size:24px;letter-spacing:-.01em;}
    .features{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;}
    .feature{border:1px solid var(--border);background:var(--surface);border-radius:16px;padding:16px;}
    .feature h3{margin:0 0 6px;font-size:16px;}
    .feature p{margin:0;color:var(--muted);line-height:1.5;font-size:14px;}
    .example{margin-top:12px;border:1px solid #7f1d1d66;background:linear-gradient(140deg,#450a0a 0%,#7f1d1d 60%,#991b1b 100%);border-radius:16px;padding:16px;color:#fff1f2;}
    .example h3{margin:0 0 4px;font-size:14px;letter-spacing:.05em;text-transform:uppercase;opacity:.95;}
    .example .headline{font-size:24px;font-weight:900;margin-bottom:6px;}
    .example p{margin:0;color:#fecdd3;line-height:1.5;}
    .chips{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;}
    .chip{border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800;border:1px solid #fecdd588;background:#fff1f526;color:#ffe4e6;}
    @media (max-width:860px){.features{grid-template-columns:1fr;}.hero{padding:22px;}.shell{padding:18px 14px 34px;}}
  </style>
</head>
<body>
  <main class='shell'>
    <section class='hero'>
      <div class='kicker'>ParlayBot · Slip Intelligence</div>
      <h1>Find the Leg That Sold Your Parlay</h1>
      <p class='hero-sub'>ParlayBot grades settled bet slips leg-by-leg, highlights the exact leg that broke the ticket, and explains the kill moment. Use the new pre-game analyzer to identify fragile legs before you place the bet.</p>
      <div class='actions'>
        <a class='btn btn-primary' href='/check?mode=settle'>Check a Settled Slip</a>
        <a class='btn btn-secondary' href='/check?mode=analyze'>Analyze a Parlay Before You Bet</a>
      </div>
    </section>

    <h2 class='section-title'>What you get</h2>
    <section class='features'>
      <article class='feature'>
        <h3>Sold Leg Detection</h3>
        <p>Pinpoint the exact leg that flipped your ticket from live to dead, with plain-language reasoning tied to the market.</p>
      </article>
      <article class='feature'>
        <h3>Kill Moment Explanation</h3>
        <p>See the specific game sequence that killed the slip so you understand not just what lost, but when and why.</p>
      </article>
      <article class='feature'>
        <h3>Pre-Game Slip Analyzer</h3>
        <p>Before locking your parlay, run an advisory pass to surface weaker legs and get a risk-forward read.</p>
      </article>
    </section>

    <section class='example'>
      <h3>Example result preview</h3>
      <div class='headline'>LOST · Sold by Luka Dončić O31.5 PTS</div>
      <p>Kill moment: Entered the 4th quarter at 26 points and finished with 30 after foul trouble limited closing usage.</p>
      <div class='chips'>
        <span class='chip'>Hit legs: 4</span>
        <span class='chip'>Missed legs: 1</span>
        <span class='chip'>Confidence: High</span>
      </div>
    </section>
  </main>
  <script>
    (function(){
      const root=document.documentElement;
      const stored=localStorage.getItem('parlay_theme_mode')||'system';
      if(stored==='light'){root.setAttribute('data-theme','light');return;}
      if(stored==='dark'){root.setAttribute('data-theme','dark');return;}
      const prefersDark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.setAttribute('data-theme',prefersDark?'dark':'light');
    })();
  </script>
</body>
</html>"""
    return HTMLResponse(html)


_TRACKER_COOKIE_NAME = 'parlay_tracker_key'


def _normalize_tracker_key(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r'[^a-z0-9]', '', value.lower())
    if len(cleaned) < 12:
        return None
    return cleaned[:64]


def _ensure_tracker_key(existing: str | None) -> str:
    normalized = _normalize_tracker_key(existing)
    if normalized:
        return normalized
    return uuid4().hex[:24]


def _slip_status_summary(legs: list[dict]) -> str:
    wins = sum(1 for leg in legs if str(leg.get('result', '')).lower() in {'win', 'push'})
    losses = sum(1 for leg in legs if str(leg.get('result', '')).lower() == 'loss')
    voids = sum(1 for leg in legs if str(leg.get('result', '')).lower() == 'void')
    unresolved = sum(1 for leg in legs if str(leg.get('result', '')).lower() in {'review', 'pending', 'unmatched'})
    graded = wins + losses
    if losses and unresolved:
        noun = 'leg' if unresolved == 1 else 'legs'
        plural = '' if losses == 1 else 'es'
        return f'Already lost · {losses} loss{plural} · {unresolved} {noun} still need review'
    if unresolved:
        return f'{wins} wins · {losses} losses · {voids} void · {unresolved} review'
    if voids:
        return f'{wins} of {graded} graded legs hit · {voids} void'
    return f'{wins} of {graded} graded legs hit'


@app.get('/check', response_class=HTMLResponse)
def public_check_page(tracker_key: str | None = Cookie(default=None, alias=_TRACKER_COOKIE_NAME)) -> HTMLResponse:
    html = '''<!doctype html>
<html>
<head>
  <title>Did This Parlay Cash?</title>
  <style>
    :root{--bg:#070b14;--bg-soft:#0b1220;--surface:#111a2d;--surface-elev:#16223a;--surface-glass:rgba(18,27,46,.82);--border:#263954;--text:#f8fbff;--muted:#95a5c4;--primary:#3b82f6;--primary-2:#60a5fa;--success:#16a34a;--danger:#dc2626;--warning:#d97706;color-scheme:dark;}
    :root[data-theme='light']{--bg:#edf3ff;--bg-soft:#e2ebfb;--surface:#ffffff;--surface-elev:#f8fbff;--surface-glass:rgba(255,255,255,.88);--border:#cfddf1;--text:#0f172a;--muted:#475569;--primary:#2563eb;--primary-2:#1d4ed8;--success:#15803d;--danger:#b91c1c;--warning:#b45309;color-scheme:light;}
    body{font-family:Inter,system-ui,Arial,Helvetica,sans-serif;margin:0;background:radial-gradient(1200px 600px at 5% -10%,#1d4ed833,transparent 65%),radial-gradient(1000px 600px at 95% -20%,#9333ea2e,transparent 62%),var(--bg);color:var(--text);}
    .shell{max-width:1080px;margin:0 auto;padding:22px 14px 56px;}
    .hero-card,.card{background:var(--surface-glass);backdrop-filter:blur(8px);border:1px solid var(--border);border-radius:20px;padding:18px;box-shadow:0 18px 35px rgba(2,6,23,.28);}
    .hero-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;}
    .hero-card{position:relative;overflow:hidden;}
    .hero-card::after{content:'';position:absolute;inset:auto -120px -120px auto;width:280px;height:280px;background:radial-gradient(circle,var(--primary) 0%,transparent 70%);opacity:.2;pointer-events:none;}
    h1{margin:0;font-size:36px;line-height:1.08;letter-spacing:-.02em;}
    p{color:var(--muted);line-height:1.5;}
    .grid{display:grid;grid-template-columns:1fr;gap:14px;align-items:start;}
    .panel-title{margin:0 0 8px;font-size:20px;}
    .status{margin-top:10px;padding:10px 12px;border-radius:12px;font-weight:600;display:none;}
    .status.show{display:block;}
    .status.success{background:#dcfce7;color:#166534;border:1px solid #86efac;}
    .status.error{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;}
    textarea,input,button,select{font:inherit;border-radius:12px;box-sizing:border-box;}
    textarea,input,select{width:100%;padding:11px 12px;border:1px solid var(--border);background:var(--bg-soft);color:var(--text);}
    textarea{min-height:190px;}
    button{margin-top:12px;padding:11px 16px;border:1px solid var(--primary-2);background:linear-gradient(180deg,var(--primary),var(--primary-2));color:#fff;cursor:pointer;font-weight:700;transition:.15s ease;}
    button:hover{filter:brightness(1.05);} button:active{transform:translateY(1px);} button[disabled]{opacity:.6;cursor:not-allowed;}
    button.sample{margin-top:0;background:transparent;color:var(--text);border:1px solid var(--border);padding:8px 12px;border-radius:999px;}
    button.secondary{background:var(--bg-soft);color:var(--text);border-color:var(--border);}
    .candidate-btn{display:inline-flex;align-items:center;gap:6px;margin-top:8px;margin-right:8px;padding:10px 14px;border-radius:999px;border:1px solid var(--border);background:var(--bg-soft);color:var(--text);cursor:pointer;pointer-events:auto;font-size:13px;font-weight:700;}
    .candidate-btn:hover{border-color:var(--primary);} .candidate-btn.selected{background:linear-gradient(180deg,var(--primary),var(--primary-2));border-color:transparent;color:#fff;box-shadow:0 8px 20px #1d4ed844;}
    .review-panel{margin-top:6px;padding:10px;border:1px solid #854d0e33;background:#f59e0b22;border-radius:10px;color:var(--text);}
    .review-title{font-size:12px;font-weight:800;letter-spacing:.02em;text-transform:uppercase;}
    .review-reason{margin-top:4px;font-size:13px;color:var(--muted);}
    #samples{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 14px;}
    .field-row{display:grid;grid-template-columns:1fr;gap:10px;}
    #uploadWrap{margin-top:12px;padding:12px;border:1px dashed var(--border);border-radius:12px;background:var(--bg-soft);position:relative;z-index:0;}
    #uploadWrap.is-busy{opacity:.72;}
    #uploadWrap.is-busy::after{content:'';position:absolute;inset:0;border-radius:12px;background:transparent;pointer-events:none;}
    #message{margin-top:12px;color:var(--primary-2);font-weight:600;}
    #resultWrap{margin-top:14px;padding:16px;display:flex;flex-direction:column;gap:12px;}
    #overall{font-size:34px;font-weight:900;border-radius:16px;padding:16px 18px;margin:0;}
    #overall.win{background:linear-gradient(135deg,#14532d,#166534);border:1px solid #22c55e;color:#f0fdf4;}
    #overall.loss{background:linear-gradient(135deg,#450a0a,#7f1d1d);border:1px solid #ef4444;color:#fff1f2;}
    #overall.review{background:linear-gradient(135deg,#422006,#78350f);border:1px solid #f59e0b;color:#fffbeb;}
    .result-summary,.result-meta,.leg-progress{display:flex;flex-wrap:wrap;gap:8px;}
    .result-chip,.meta-chip,.leg-progress-chip{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:999px;padding:6px 11px;font-size:12px;font-weight:700;background:var(--bg-soft);color:var(--text);}
    .result-chip.win,.leg-progress-chip.win{border-color:#22c55e;color:#15803d;}
    .result-chip.loss,.leg-progress-chip.loss{border-color:#ef4444;color:#b91c1c;}
    .result-chip.review,.leg-progress-chip.review{border-color:#f59e0b;color:#b45309;}
    .sold-hero{position:relative;overflow:hidden;border:1px solid #7f1d1d55;background:linear-gradient(140deg,#450a0a 0%,#7f1d1d 48%,#991b1b 100%);color:#fff1f2;border-radius:16px;padding:14px;box-shadow:0 12px 24px rgba(127,29,29,.3);}
    .sold-hero::after{content:'';position:absolute;right:-70px;top:-65px;width:180px;height:180px;border-radius:50%;background:radial-gradient(circle,#fca5a566 0%,transparent 70%);pointer-events:none;}
    .sold-hero-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;position:relative;z-index:1;}
    .sold-kicker{font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.86;font-weight:800;}
    .sold-title{font-size:22px;font-weight:900;line-height:1.1;margin-top:2px;}
    .sold-hero-leg{margin-top:8px;font-size:14px;font-weight:700;position:relative;z-index:1;}
    .sold-summary{margin-top:8px;font-size:13px;color:#ffe4e6;position:relative;z-index:1;}
    .sold-meta-grid{margin-top:10px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;position:relative;z-index:1;}
    .sold-meta-item{border:1px solid #fecdd533;background:#fff1f51a;border-radius:10px;padding:8px;}
    .sold-meta-label{font-size:11px;opacity:.85;text-transform:uppercase;letter-spacing:.04em;}
    .sold-meta-value{margin-top:3px;font-size:15px;font-weight:800;color:#fff;}
    .sold-context{margin-top:10px;padding:9px;border-radius:10px;background:#fff1f51f;border:1px solid #fecdd544;color:#ffe4e6;font-size:13px;position:relative;z-index:1;}
    .sold-kill-moment{margin-top:10px;padding:10px;border-radius:10px;background:#fff1f520;border:1px solid #fecdd544;color:#ffe4e6;position:relative;z-index:1;}
    .sold-kill-title{font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;opacity:.9;}
    .sold-kill-body{margin-top:6px;font-size:13px;line-height:1.4;color:#fff1f2;}
    .sold-kill-meta{margin-top:6px;font-size:11px;opacity:.85;color:#fecdd5;}
    .sold-other-legs{margin-top:10px;border-radius:12px;border:1px solid #fecdd544;background:#fff1f517;position:relative;z-index:1;}
    .sold-other-legs summary{cursor:pointer;list-style:none;padding:10px 12px;font-size:12px;font-weight:800;color:#ffe4e6;}
    .sold-other-legs summary::-webkit-details-marker{display:none;}
    .sold-other-list{padding:0 12px 10px;display:flex;flex-direction:column;gap:8px;}
    .sold-other-item{border-top:1px solid #fecdd533;padding-top:8px;font-size:12px;color:#ffe4e6;}
    .sold-other-item:first-child{border-top:none;padding-top:0;}
    .closeness-card{border:1px solid var(--border);border-radius:12px;padding:12px;background:var(--bg-soft);color:var(--text);}
    .closeness-title{font-size:18px;font-weight:800;line-height:1.2;}
    .closeness-copy{margin-top:6px;font-size:14px;color:var(--muted);}
    .closeness-meta{margin-top:10px;display:grid;grid-template-columns:1fr;gap:6px;font-size:13px;}
    .autopsy-card.soft{border:1px solid #854d0e33;background:#fed7aa33;color:#92400e;border-radius:12px;padding:12px;}
    .recent-slip-card{display:flex;justify-content:space-between;align-items:stretch;gap:14px;padding:12px;border:1px solid var(--border);border-radius:14px;background:var(--surface-elev);}
    .recent-slip-main{min-width:0;display:flex;flex-direction:column;gap:6px;}.recent-slip-summary{font-weight:800;font-size:15px;line-height:1.2;}
    .recent-slip-meta,.recent-slip-preview{font-size:12px;color:var(--muted);} .recent-slip-preview{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .recent-slip-side{display:flex;flex-direction:column;gap:8px;align-items:flex-end;}.recent-slip-progress{width:100%;height:6px;border-radius:999px;background:var(--bg-soft);overflow:hidden;}
    .recent-slip-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#22c55e,#16a34a);} .recent-slip-progress-fill.review{background:linear-gradient(90deg,#f59e0b,#d97706);} .recent-slip-progress-fill.loss{background:linear-gradient(90deg,#f43f5e,#dc2626);}
    .empty-polish{border:1px dashed var(--border);border-radius:12px;padding:12px;background:var(--bg-soft);color:var(--muted);}
    .mode-toggle{display:inline-flex;gap:6px;padding:6px;border-radius:999px;border:1px solid var(--border);background:var(--bg-soft);margin-top:10px;}
    .mode-option{margin-top:0;padding:9px 14px;border-radius:999px;border:1px solid transparent;background:transparent;color:var(--muted);font-size:13px;font-weight:800;}
    .mode-option.active{background:linear-gradient(180deg,var(--primary),var(--primary-2));color:#fff;box-shadow:0 8px 20px #1d4ed844;}
    .mode-description{margin-top:10px;padding:10px 12px;border:1px solid var(--border);border-radius:12px;background:var(--bg-soft);font-size:13px;color:var(--muted);}
    .mode-description strong{color:var(--text);}
    .mode-hidden{display:none !important;}
    .mode-muted{opacity:.5;}
    .advisory-banner{margin-top:10px;padding:12px;border-radius:12px;border:1px solid #facc15;background:linear-gradient(180deg,#fef9c3,#fef3c7);color:#92400e;font-size:13px;font-weight:700;}
    .risk-card{padding:10px;border:1px solid var(--border);border-radius:12px;background:var(--surface-elev);}
    .risk-chip{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;}
    .risk-chip.low{background:#dcfce7;color:#166534;}
    .risk-chip.medium{background:#fef3c7;color:#92400e;}
    .risk-chip.high{background:#fee2e2;color:#b91c1c;}
    table{width:100%;border-collapse:collapse;} th,td{padding:8px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top;}
    a{color:var(--primary);} code{background:var(--bg-soft);padding:2px 6px;border-radius:6px;color:var(--primary-2);} .loading-skeleton{display:none;grid-template-columns:1fr;gap:8px;}
    .loading-skeleton.show{display:grid;} .loading-skeleton div{height:14px;border-radius:8px;background:linear-gradient(90deg,var(--bg-soft),var(--surface),var(--bg-soft));background-size:200% 100%;animation:pulse 1.2s infinite;}
    @keyframes pulse{0%{background-position:200% 0;}100%{background-position:-200% 0;}}
    @media (min-width:860px){.shell{padding:30px 20px 60px;}.grid{grid-template-columns:1.05fr .95fr;}.field-row{grid-template-columns:1fr 1fr;}.hero-actions{display:flex;gap:10px;align-items:center;}}
    @media (max-width:640px){h1{font-size:31px;} .recent-slip-card{flex-direction:column;}.recent-slip-side{align-items:flex-start;} .sold-meta-grid{grid-template-columns:1fr;} .sold-title{font-size:19px;} table,thead,tbody{display:block;} thead{display:none;} tr{display:block;margin-bottom:10px;border:1px solid var(--border);border-radius:14px;background:var(--bg-soft);padding:12px;} td{text-align:left;padding:4px 0;display:block;border:none;} td.leg-result-cell{display:none;}}
  </style>
</head>
<body>
  <div class='shell'>
    <div class='hero-card'>
      <div class='hero-top'>
        <div>
          <h1>Did This Parlay Cash?</h1>
          <p>Fast, accurate slip grading with a premium review workflow. Paste text, upload a screenshot, and validate every leg without leaving this page.</p>
        </div>
        <div class='hero-actions'>
          <select id='themeMode' aria-label='Theme mode'>
            <option value='system'>System theme</option>
            <option value='dark'>Dark</option>
            <option value='light'>Light</option>
          </select>
        </div>
      </div>
      <p style='margin-top:0;font-size:12px;'>MLB/NFL grading is beta preview only. NBA grading is currently the most reliable.</p>
      <div>
        <div style='font-size:11px;font-weight:800;letter-spacing:.06em;color:var(--muted);text-transform:uppercase;'>Mode</div>
        <div class='mode-toggle' role='tablist' aria-label='Slip mode selector'>
          <button id='modeSettleBtn' type='button' class='mode-option active' role='tab' aria-selected='true'>Settle Slip</button>
          <button id='modeAnalyzeBtn' type='button' class='mode-option' role='tab' aria-selected='false'>Analyze Slip</button>
        </div>
      </div>
      <div id='samples'>
        <button type='button' class='sample' data-sample='sample_nba_props'>NBA Props</button>
        <button type='button' class='sample' data-sample='sample_mlb'>MLB Mix (Beta)</button>
        <button type='button' class='sample' data-sample='sample_nfl'>NFL Mix (Beta)</button>
      </div>
    </div>
    <div class='grid' style='margin-top:14px;'>
      <div class='card'>
        <h2 class='panel-title'>Slip input</h2>
        <div id='modeDescription' class='mode-description'><strong>Settle Slip:</strong> Post-game grading for settled bets with per-leg outcomes and explanations.</div>
        <form id='checkForm'>
          <textarea id='slip' placeholder='Jokic over 24.5 points
Denver ML
Murray over 2.5 threes'></textarea>
          <div id='nameSuggestions' style='display:none;margin-top:8px;padding:10px;border:1px solid var(--border);border-radius:10px;background:var(--surface);'></div>
          <div class='field-row' style='margin-top:10px;'>
            <div><input id='stakeAmount' type='number' min='0.01' step='0.01' placeholder='Stake amount (optional)'></div>
            <div><input id='slipDate' type='date' placeholder='Bet Date (optional, recommended)'></div>
          </div>
          <div style='font-size:12px;color:var(--muted);margin-top:4px;'>Bet date is optional but strongly recommended for NBA props.</div>
          <label style='display:flex;align-items:center;gap:8px;margin-top:10px;'><input id='searchHistorical' type='checkbox' style='width:auto;'><span>Search historical results</span></label>
          <div id='uploadWrap'>
            <label for='slipImage'><strong>Upload slip screenshot</strong></label>
            <div style='font-size:12px;color:var(--muted);margin:4px 0 8px;'>PNG/JPG up to 8MB. We parse first, then you can review before grading. One leg per line.</div>
            <input id='slipImage' type='file' accept='image/*'>
            <button id='removeScreenshotBtn' class='secondary' type='button' style='margin-top:8px;display:none;'>Remove Screenshot</button>
          </div>
          <button id='checkBtn' type='button'>Check Slip</button>
        </form>
        <div id='message'></div>
        <div id='actionStatus' class='status' role='status' aria-live='polite'></div>
      </div>
      <div class='card'>
        <div style='display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;'>
          <strong>My Slips</strong>
          <button id='refreshRecentBtn' class='secondary' type='button' style='margin-top:0;'>Refresh</button>
        </div>
        <div id='recentSlipsEmpty' class='empty-polish' style='margin-top:10px;'>No saved slips yet — run a check and it’ll show up here.</div>
        <div id='recentSlipsList' style='display:flex;flex-direction:column;gap:8px;margin-top:10px;'></div>
      </div>
    </div>
    <div id='resultWrap' hidden class='card'>
      <div id='overall'></div>
      <div id='resultSummary' class='result-summary' hidden></div>
      <div id='legProgressStrip' class='leg-progress' hidden></div>
      <div id='metaSummary' class='result-meta' hidden></div>
      <div id='diedHere' hidden></div>
      <div id='payoutOut' style='margin:8px 0;color:var(--muted);'></div>
      <div id='gradingSkeleton' class='loading-skeleton'><div></div><div></div><div></div></div>
      <details><summary>Show technical details</summary><div id='debugOut' style='margin:8px 0 12px;color:var(--muted);'></div></details>
      <table>
        <thead><tr><th id='colLegHeader'>Leg</th><th id='colResultHeader'>Result</th><th id='colThirdHeader'>Matched event</th></tr></thead>
        <tbody id='legsBody'></tbody>
      </table>
      <div id='summaryWrap'>
        <div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;'>
          <button id='copyBtn' class='secondary' type='button' disabled>Copy Summary</button>
          <button id='copyLinkBtn' class='secondary' type='button' disabled>Copy Public Link</button>
          <button id='openLinkBtn' class='secondary' type='button' disabled>Open Public Result</button>
          <button id='downloadCardBtn' class='secondary' type='button' disabled>Download Share Card</button>
        </div>
        <textarea id='summaryOut' readonly placeholder='Summary will appear here after checking a slip.'></textarea>
        <canvas id='shareCardCanvas' width='1080' height='1350' style='display:none;'></canvas>
      </div>
    </div>
  </div>
<script>
    const sampleSlips={
      sample_nba_props:'Jokic over 24.5 points\\nMurray over 2.5 threes\\nDenver ML',
      sample_mlb:'Dodgers ML\\nYankees +1.5\\nGame Total Over 8.5',
      sample_nfl:'Chiefs ML\\nMahomes over 265.5 passing yards\\nKelce over 68.5 receiving yards'
    };
    const form=document.getElementById('checkForm');
    const modeSettleBtn=document.getElementById('modeSettleBtn');
    const modeAnalyzeBtn=document.getElementById('modeAnalyzeBtn');
    const modeDescription=document.getElementById('modeDescription');
    const slip=document.getElementById('slip');
    const stakeAmount=document.getElementById('stakeAmount');
    const slipImage=document.getElementById('slipImage');
    const uploadWrap=document.getElementById('uploadWrap');
    const removeScreenshotBtn=document.getElementById('removeScreenshotBtn');
    const slipDate=document.getElementById('slipDate');
    const searchHistorical=document.getElementById('searchHistorical');
    const btn=document.getElementById('checkBtn');
    const copyBtn=document.getElementById('copyBtn');
    const summaryOut=document.getElementById('summaryOut');
    const copyLinkBtn=document.getElementById('copyLinkBtn');
    const openLinkBtn=document.getElementById('openLinkBtn');
    const downloadCardBtn=document.getElementById('downloadCardBtn');
    const shareCardCanvas=document.getElementById('shareCardCanvas');
    const msg=document.getElementById('message');
    const nameSuggestions=document.getElementById('nameSuggestions');
    const actionStatus=document.getElementById('actionStatus');
    const recentSlipsList=document.getElementById('recentSlipsList');
    const recentSlipsEmpty=document.getElementById('recentSlipsEmpty');
    const refreshRecentBtn=document.getElementById('refreshRecentBtn');
    const themeMode=document.getElementById('themeMode');
    const wrap=document.getElementById('resultWrap');
    const overall=document.getElementById('overall');
    const resultSummary=document.getElementById('resultSummary');
    const metaSummary=document.getElementById('metaSummary');
    const legProgressStrip=document.getElementById('legProgressStrip');
    const payoutOut=document.getElementById('payoutOut');
    const diedHere=document.getElementById('diedHere');
    const debugOut=document.getElementById('debugOut');
    const legsBody=document.getElementById('legsBody');
    const colLegHeader=document.getElementById('colLegHeader');
    const colResultHeader=document.getElementById('colResultHeader');
    const colThirdHeader=document.getElementById('colThirdHeader');
    const gradingSkeleton=document.getElementById('gradingSkeleton');
    const resultLabel={win:'Win',loss:'Loss',pending:'Pending',push:'Push',void:'Void',review:'Review',unmatched:'Review'};
    const resultEmoji={win:'✅',loss:'❌',pending:'⏳',push:'➖',void:'🚫',review:'🧐',unmatched:'🧐'};
    const screenshotGradeEndpoint='/ingest/screenshot/grade';
    const slipModeStorageKey='parlay_slip_mode';
    const modeSettle='settle';
    const modeAnalyze='analyze';
    const overallLabel={cashed:'CASHED',lost:'LOST',still_live:'STILL LIVE',needs_review:'NEEDS REVIEW'};
    const overallTone={cashed:'win',lost:'loss',still_live:'review',needs_review:'review'};
    const emptyTextMessage='Paste at least one leg first.';
    let selectedGameByLegId={};
    let selectedPlayerByLegId={};
    let legUiStateByLegId={};
    let latestPublicUrl='';
    let latestResultPayload=null;
    let screenshotNeedsParse=false;
    let screenshotParseInFlight=false;
    let parsedScreenshotSignature=null;
    let latestPlayerSuggestions=[];
    let activeSlipMode=modeSettle;

    function applySlipMode(mode){
      activeSlipMode=mode===modeAnalyze?modeAnalyze:modeSettle;
      localStorage.setItem(slipModeStorageKey,activeSlipMode);
      const settleSelected=activeSlipMode===modeSettle;
      modeSettleBtn.classList.toggle('active',settleSelected);
      modeAnalyzeBtn.classList.toggle('active',!settleSelected);
      modeSettleBtn.setAttribute('aria-selected',String(settleSelected));
      modeAnalyzeBtn.setAttribute('aria-selected',String(!settleSelected));
      btn.textContent=settleSelected?'Check Slip':'Analyze Slip';
      uploadWrap.classList.toggle('mode-hidden',!settleSelected);
      searchHistorical.closest('label').classList.toggle('mode-hidden',!settleSelected);
      if(settleSelected){
        modeDescription.innerHTML='<strong>Settle Slip:</strong> Post-game grading for settled bets with per-leg outcomes and explanations.';
        colLegHeader.textContent='Leg';
        colResultHeader.textContent='Result';
        colThirdHeader.textContent='Matched event';
      }else{
        modeDescription.innerHTML='<strong>Analyze Slip:</strong> Before you bet, get a pre-game risk read and weakest-leg advisory. This mode is advisory only.';
        colLegHeader.textContent='Leg';
        colResultHeader.textContent='Risk';
        colThirdHeader.textContent='Advisory';
      }
    }

    function initSlipMode(){
      const params=new URLSearchParams(window.location.search);
      const queryMode=params.get('mode');
      const querySelected=queryMode===modeAnalyze?modeAnalyze:(queryMode===modeSettle?modeSettle:null);
      const stored=localStorage.getItem(slipModeStorageKey);
      applySlipMode(querySelected||(stored===modeAnalyze?modeAnalyze:modeSettle));
      modeSettleBtn.addEventListener('click',()=>applySlipMode(modeSettle));
      modeAnalyzeBtn.addEventListener('click',()=>applySlipMode(modeAnalyze));
    }

    function applyTheme(mode){
      const root=document.documentElement;
      if(mode==='light'){root.setAttribute('data-theme','light'); return;}
      if(mode==='dark'){root.setAttribute('data-theme','dark'); return;}
      const prefersDark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.setAttribute('data-theme',prefersDark?'dark':'light');
    }

    function initTheme(){
      const stored=localStorage.getItem('parlay_theme_mode')||'system';
      themeMode.value=stored;
      applyTheme(stored);
      themeMode.addEventListener('change',()=>{
        const next=themeMode.value||'system';
        localStorage.setItem('parlay_theme_mode',next);
        applyTheme(next);
      });
    }

    // Legacy regression-test literals kept for compatibility:
    // const canPickGame=(item.result==='review'||showGamePicker)&&candidateGames.length>0
    // const canPickPlayer=(item.result==='review'||showPlayerPicker)&&candidatePlayers.length>0&&String(item.sport||item.leg?.sport||'NBA')==='NBA'&&(!playerSelectionApplied||showPlayerPicker);
    // const shouldShowPicker=(item.result==='review'||showPlayerPicker)&&candidatePlayers.length>0&&String(item.sport||item.leg?.sport||'NBA')==='NBA'&&(!playerSelectionApplied||showPlayerPicker);
    // const statusBadge=reviewStatusLabel(details);
    // details.player_resolution_status==='fuzzy_resolved'
    // selection_source
    // original_typed_player_name
    // pickerLabel.textContent='Multiple games found. Choose the correct one.';
    // pickerLabel.textContent='Did you mean?';
    // changePlayerBtn.textContent='Change player'
    // resetPlayerBtn.textContent='Reset selected player'
    // changeGameBtn.textContent='Change game';
    // resetGameBtn.textContent='Reset selected game';
    // resetGameBtn.textContent='Auto-match (clear manual selection)'
    // <strong>Original typed leg:</strong>
    // <strong>Override used for grading:</strong>
    // <strong>Override outcome:</strong>
    // <strong>Final settlement:</strong>
    // Player selection succeeded, but another downstream grading validation still requires review.
    // Selected game could not be applied; choose one of the listed games.
    // Resolved from likely player name match
    // Player resolution method:
    // Player resolution confidence:
    // Player resolution mode:
    // Canonical matched player:
    // const canPickGame=(item.result==='review'||showGamePicker)&&candidateGames.length>0;
    // const nextSelection={...selectedPlayerByLegId};
    // <span class='result-chip'>${counts.total} Legs</span>
    // <span class='result-chip'>${counts.won} Won</span>
    // <span class='result-chip'>${counts.lost} Lost</span>
    // <span class='result-chip'>${counts.review} Review</span>
    // suggestion.textContent=didYouMeanText;
    // Possible games
    // if(parsedLegs.length){slip.value=parsedLegs.join('\\n');}
    // else if(body.cleaned_text){slip.value=body.cleaned_text;}

    function statusBadgeTone(status){
      if(status==='cashed'){return 'win';}
      if(status==='lost'){return 'loss';}
      return 'review';
    }

    function statusBadgeLabel(status){
      if(status==='cashed'){return 'Won';}
      if(status==='lost'){return 'Lost';}
      return 'Needs review';
    }

    function renderRecentSlips(items){
      recentSlipsList.innerHTML='';
      const rows=Array.isArray(items)?items:[];
      recentSlipsEmpty.style.display=rows.length?'none':'block';
      for(const item of rows){
        const row=document.createElement('div');
        row.className='recent-slip-card';

        const left=document.createElement('div');
        left.className='recent-slip-main';

        const summary=document.createElement('div');
        summary.className='recent-slip-summary';
        summary.textContent=item.summary||'Needs review';

        const meta=document.createElement('div');
        meta.className='recent-slip-meta';
        meta.textContent=`${item.bet_date||'No bet date'} · ${item.checked_at_label||'just now'}`;

        const preview=document.createElement('div');
        preview.className='recent-slip-preview';
        preview.textContent=item.preview_text||'';

        const progressWrap=document.createElement('div');
        progressWrap.className='recent-slip-progress';
        const progressFill=document.createElement('div');
        const tone=statusBadgeTone(item.overall_result);
        progressFill.className=`recent-slip-progress-fill ${tone}`;
        const summaryText=String(item.summary||'');
        const hitMatch=summaryText.match(/(\d+)\s*\/\s*(\d+)\s*hit/i);
        const unresolvedMatch=summaryText.match(/(\d+)\s+leg(?:s)?\s+unresolved/i);
        let progressRatio=0;
        if(hitMatch){
          const hits=Number(hitMatch[1]);
          const total=Number(hitMatch[2]);
          progressRatio=total>0?Math.max(0,Math.min(1,hits/total)):0;
        }else if(unresolvedMatch){
          const unresolved=Number(unresolvedMatch[1]);
          const totalGuess=(item.preview_text||'').split(' · ')[0].split('|').length;
          progressRatio=totalGuess>0?Math.max(0,Math.min(1,(totalGuess-unresolved)/totalGuess)):0.5;
        }else{
          progressRatio=tone==='win'?1:(tone==='loss'?0.35:0.5);
        }
        progressFill.style.width=`${Math.round(progressRatio*100)}%`;
        progressWrap.appendChild(progressFill);

        left.append(summary,meta,progressWrap,preview);

        const right=document.createElement('div');
        right.className='recent-slip-side';
        const badge=document.createElement('span');
        badge.className=`result-chip ${tone}`;
        badge.textContent=statusBadgeLabel(item.overall_result);

        const open=document.createElement('button');
        open.type='button';
        open.className='secondary';
        open.style.marginTop='0';
        open.textContent='Open';
        open.disabled=!item.public_url;
        open.addEventListener('click',()=>{ if(item.public_url){window.open(item.public_url,'_blank','noopener');}});

        right.append(badge,open);
        row.append(left,right);
        recentSlipsList.appendChild(row);
      }
    }


    async function loadRecentSlips(){
      try{
        const res=await fetch('/my-slips');
        const body=await res.json();
        if(!res.ok){throw new Error(body.detail||'Failed to load slips');}
        renderRecentSlips(body.items||[]);
      }catch(err){
        recentSlipsEmpty.style.display='block';
        recentSlipsEmpty.textContent='Could not load saved checks right now.';
      }
    }

    function getScreenshotSignature(file){
      if(!file){return null;}
      return `${file.name||'upload'}:${file.size||0}:${file.lastModified||0}`;
    }

    function showActionStatus(text,type='success'){
      actionStatus.textContent=text;
      actionStatus.className=`status show ${type}`;
    }

    function clearActionStatus(){
      actionStatus.textContent='';
      actionStatus.className='status';
    }

    function setScreenshotUploadBusy(isBusy){
      screenshotParseInFlight=Boolean(isBusy);
      slipImage.disabled=screenshotParseInFlight;
      removeScreenshotBtn.disabled=screenshotParseInFlight;
      uploadWrap.classList.toggle('is-busy',screenshotParseInFlight);
    }

    function resetScreenshotInputValue(){
      slipImage.value='';
    }

    function resetManualSelectionState(){
      selectedGameByLegId={};
      selectedPlayerByLegId={};
      legUiStateByLegId={};
    }

    function clearScreenshotSelection({keepMessage=false}={}){
      resetScreenshotInputValue();
      removeScreenshotBtn.style.display='none';
      screenshotNeedsParse=false;
      parsedScreenshotSignature=null;
      setScreenshotUploadBusy(false);
      if(!keepMessage){ msg.textContent=''; }
      latestPlayerSuggestions=[];
      renderNameSuggestions();
      if((debugOut.textContent||'').includes('OCR extracted text:')){ debugOut.innerHTML=''; }
    }

    slipImage.addEventListener('change',()=>{
      if(screenshotParseInFlight){return;}
      const file=slipImage.files&&slipImage.files[0];
      const nextSignature=getScreenshotSignature(file);
      removeScreenshotBtn.style.display=file?'inline-block':'none';
      screenshotNeedsParse=Boolean(file)&&nextSignature!==parsedScreenshotSignature;
    });

    removeScreenshotBtn.addEventListener('click',()=>{
      clearScreenshotSelection({keepMessage:true});
      if(msg.textContent&&msg.textContent.includes('Screenshot')){
        msg.textContent='Screenshot removed. You can keep editing the text or upload another screenshot.';
      }
      slip.focus();
    });

    slip.addEventListener('input',()=>{
      resetManualSelectionState();
    });
    document.querySelectorAll('[data-sample]').forEach((node)=>{
      node.addEventListener('click',()=>{
        const key=node.getAttribute('data-sample');
        slip.value=sampleSlips[key]||'';
        slip.focus();
      });
    });

    function reviewStatusLabel(details){
      if(!details||!details.player_resolution_status){return null;}
      const labels={fuzzy_resolved:'Resolved',ambiguous:'Ambiguous',unresolved:'Unresolved'};
      return labels[details.player_resolution_status]||'Review';
    }

    function isUnsupportedSpecialMarketReview(item){
      const details=item.review_details||item.resolution_details||null;
      const reasonCode=String(details?.review_reason_code||'').toUpperCase();
      const unmatchedReason=String(item.unmatched_reason_code||'').toLowerCase();
      const settlementReason=String(item.settlement_reason_code||'').toLowerCase();
      const rawContext=[
        item.leg,
        item.normalized_market,
        item.settlement_reason_text,
        item.review_reason,
        item.review_reason_text,
        details?.review_reason_text,
        ...(item.notes||[]),
        ...(item.event_resolution_warnings||[]),
      ].join(' ').toLowerCase();
      const hasSpecialMarketHint=/(first\\s+half|first\\s+[0-9]+\\s+minutes|first\\s+to|race\\s+to|special|time-window|time window|sequence)/.test(rawContext);
      return reasonCode==='UNSUPPORTED_MARKET'
        || unmatchedReason==='unsupported_market'
        || settlementReason==='unsupported_market'
        || (rawContext.includes('unsupported market')||rawContext.includes('market mapping missing'))
        || hasSpecialMarketHint;
    }

    function unsupportedMarketBadgeLabel(item){
      const context=[item.leg,item.normalized_market,item.settlement_reason_text,...(item.notes||[])].join(' ').toLowerCase();
      if(/first\\s+half|first\\s+[0-9]+\\s+minutes|time-window|time window/.test(context)){return 'Time-window market';}
      if(/race\\s+to|first\\s+to|sequence/.test(context)){return 'Special market';}
      return 'Unsupported market';
    }

    function bestReviewReason(item){
      const details=item.review_details||item.resolution_details||null;
      if(isUnsupportedSpecialMarketReview(item)){
        return 'Recognized but not fully supported yet. This market was kept for review instead of being dropped. Special/time-window market support is still limited.';
      }
      if(details&&details.review_reason_text){return details.review_reason_text;}
      return item.event_review_reason_text||item.review_reason_text||item.did_you_mean||item.review_reason||item.explanation_reason||'Needs manual review. We could not confidently resolve this leg.';
    }

    function overrideStatusText(item,{playerSelectionApplied,eventSelectionApplied,overrideUsedForGrading}){
      if(overrideUsedForGrading){
        return 'Manual selection used for grading';
      }
      if(playerSelectionApplied){
        return 'Player selected, but not used in final grading';
      }
      if(eventSelectionApplied){
        return 'Game selected, but not used in final grading';
      }
      return null;
    }

    function renderRows(legs){
      legsBody.innerHTML='';
      for(const [index,item] of (legs||[]).entries()){
        const legId=String(item.leg_id ?? index);
        const existingState=legUiStateByLegId[legId]||{};
        const hasCurrentCandidates=(item.candidate_games||[]).length>0;
        const hasCurrentPlayerCandidates=(item.candidate_players||[]).length>0;
        const nextState={
          ...existingState,
          originalCandidateEvents:existingState.originalCandidateEvents||(item.candidate_games||[]),
          originalCandidatePlayers:existingState.originalCandidatePlayers||(item.candidate_players||[]),
          wasManuallySelected:Boolean(selectedGameByLegId[legId]),
          showPlayerPicker:Boolean(existingState.showPlayerPicker),
          showGamePicker:Boolean(existingState.showGamePicker),
        };
        if(hasCurrentCandidates&&!existingState.wasManuallySelected){
          nextState.originalCandidateEvents=item.candidate_games||[];
          if(hasCurrentPlayerCandidates){ nextState.originalCandidatePlayers=item.candidate_players||[]; }
        }
        legUiStateByLegId={...legUiStateByLegId,[legId]:nextState};

        const tr=document.createElement('tr');
        const legCell=document.createElement('td');
        const resultCell=document.createElement('td');
        const eventCell=document.createElement('td');

        const status=item.result||'review';
        const legText=String(item.leg||'—');
        legCell.innerHTML=`<div style="font-weight:700;">${resultEmoji[status]||'🧐'} ${escapeHtml(legText)}</div>`;
        if(item.actual_value!==null&&item.actual_value!==undefined){
          legCell.innerHTML+=`<div style="margin-top:4px;font-size:12px;color:#cbd5e1;">Actual: ${escapeHtml(String(item.actual_value))}</div>`;
        }
        resultCell.className='leg-result-cell';

        if(item.matched_event){
          legCell.innerHTML+=`<div style="margin-top:4px;font-size:12px;color:#cbd5e1;">Game: ${escapeHtml(item.matched_event)}</div>`;
        }

        const needsReview=status==='review'||status==='unmatched';
        if(needsReview){
          const unsupportedMarketReview=isUnsupportedSpecialMarketReview(item);
          const reviewBadge=unsupportedMarketReview
            ?`<div class='review-title'>${escapeHtml(unsupportedMarketBadgeLabel(item))}</div>`
            :'';
          legCell.innerHTML+=`<div class='review-panel'>${reviewBadge}<div class='review-reason'>${escapeHtml(bestReviewReason(item)||'We could not confidently resolve this leg yet.')}</div></div>`;
        }

        const candidateGames=(item.candidate_games||[]).length
          ?(item.candidate_games||[])
          :(nextState.wasManuallySelected ? (nextState.originalCandidateEvents||[]) : []);
        const selectedGameId=selectedGameByLegId[legId]||item.selected_event_id||'';
        const showGamePicker=Boolean(nextState.showGamePicker);
        const canPickGame=(needsReview||showGamePicker)&&candidateGames.length>0;
        if(canPickGame){
          const pickerWrap=document.createElement('div');
          pickerWrap.style.marginTop='8px';
          pickerWrap.innerHTML=`<div style="font-size:12px;font-weight:700;">Choose the correct game:</div>`;
          candidateGames.forEach((game)=>{
            const pickBtn=document.createElement('button');
            pickBtn.type='button';
            pickBtn.className='secondary candidate-btn';
            const datePart=game.event_date?` — ${game.event_date}`:'';
            pickBtn.textContent=`${game.event_label||game.event_id}${datePart}`;
            if(selectedGameId&&selectedGameId===game.event_id){pickBtn.classList.add('selected');}
            pickBtn.addEventListener('click',()=>{
              if(!game.event_id){return;}
              selectedGameByLegId={...selectedGameByLegId,[legId]:game.event_id};
              legUiStateByLegId={...legUiStateByLegId,[legId]:{...nextState,wasManuallySelected:true,showGamePicker:false}};
              submitCheck();
            });
            pickerWrap.appendChild(pickBtn);
          });
          const resetGameBtn=document.createElement('button');
          resetGameBtn.type='button';
          resetGameBtn.className='secondary candidate-btn';
          resetGameBtn.textContent='Auto-match (clear manual selection)';
          resetGameBtn.addEventListener('click',()=>{
            const nextSelection={...selectedGameByLegId};
            delete nextSelection[legId];
            selectedGameByLegId=nextSelection;
            legUiStateByLegId={...legUiStateByLegId,[legId]:{...nextState,wasManuallySelected:false,showGamePicker:false}};
            submitCheck();
          });
          pickerWrap.appendChild(resetGameBtn);
          eventCell.appendChild(pickerWrap);
        }

        const candidatePlayers=((item.candidate_players||[]).length?(item.candidate_players||[]):(nextState.originalCandidatePlayers||[]))
          .filter((candidate)=>candidate&&candidate.player_name);
        const selectedPlayerId=selectedPlayerByLegId[legId]||item.selected_player_id||'';
        const showPlayerPicker=Boolean(nextState.showPlayerPicker);
        const canPickPlayer=(needsReview||showPlayerPicker)&&candidatePlayers.length>0&&String(item.sport||item.leg?.sport||'NBA')==='NBA';
        if(canPickPlayer){
          const pickerWrap=document.createElement('div');
          pickerWrap.style.marginTop='8px';
          pickerWrap.innerHTML=`<div style="font-size:12px;font-weight:700;">Choose the correct player:</div>`;
          candidatePlayers.forEach((candidate)=>{
            const pickBtn=document.createElement('button');
            pickBtn.type='button';
            pickBtn.className='secondary candidate-btn';
            const teamText=candidate.team_name?` (${candidate.team_name})`:'';
            pickBtn.textContent=`${candidate.player_name}${teamText}`;
            if(selectedPlayerId&&selectedPlayerId===candidate.player_id){pickBtn.classList.add('selected');}
            pickBtn.addEventListener('click',()=>{
              if(!candidate.player_id){return;}
              selectedPlayerByLegId={...selectedPlayerByLegId,[legId]:candidate.player_id};
              legUiStateByLegId={...legUiStateByLegId,[legId]:{...nextState,showPlayerPicker:false}};
              submitCheck();
            });
            pickerWrap.appendChild(pickBtn);
          });
          eventCell.appendChild(pickerWrap);
        }

        tr.appendChild(legCell);
        tr.appendChild(resultCell);
        tr.appendChild(eventCell);
        legsBody.appendChild(tr);
      }
    }


    function buildSummary(payload){
      const lines=['Checked on ParlayBot',''];
      (payload.legs||[]).forEach((item)=>lines.push(`${item.leg} ${resultEmoji[item.result]||'🧐'}`));
      lines.push('');
      lines.push(`Parlay: ${overallLabel[payload.parlay_result]||'NEEDS REVIEW'}`);
      return lines.join('\\n');
    }



    function countLegResults(legs){
      const counts={total:0,won:0,lost:0,review:0,void:0,pending:0};
      for(const item of (legs||[])){
        counts.total+=1;
        const normalized=item.result==='unmatched'?'review':item.result;
        if(normalized==='win'){counts.won+=1;}
        else if(normalized==='loss'){counts.lost+=1;}
        else if(normalized==='review'){counts.review+=1;}
        else if(normalized==='void'){counts.void+=1;}
        else if(normalized==='pending'){counts.pending+=1; counts.review+=1;}
      }
      return counts;
    }

    function shortLegLabel(item){
      const text=String(item.parsed_player_name||item.player_name||item.leg||'Leg').trim();
      const market=String(item.normalized_market||item.market_type||'').toLowerCase();
      const statMap={
        player_points:'PTS',player_rebounds:'REB',player_assists:'AST',player_threes:'3PM',
        player_pa:'PA',player_pr:'PR',player_ra:'RA',player_pra:'PRA'
      };
      const stat=statMap[market]||(
        market.includes('assists')?'AST':market.includes('rebounds')?'REB':market.includes('threes')?'3PM':market.includes('points')?'PTS':'LEG'
      );
      if(!text){return stat;}
      const parts=text.split(/\s+/);
      const base=parts.length===1?parts[0].slice(0,10):`${parts[0]} ${parts[parts.length-1].replace(/[^A-Za-z]/g,'').slice(0,1)}`.trim();
      return `${base} ${stat}`.trim();
    }

    function renderProgressStrip(legs){
      const chips=(legs||[]).map((item)=>{
        const state=item.result==='unmatched'?'review':(item.result||'review');
        const emoji=resultEmoji[state]||'🧐';
        return `<span class='leg-progress-chip ${state}'>${escapeHtml(shortLegLabel(item))} ${emoji}</span>`;
      });
      legProgressStrip.innerHTML=chips.join('');
      legProgressStrip.hidden=!chips.length;
    }

    function asNumber(value){
      const n=Number(value);
      return Number.isFinite(n)?n:null;
    }

    function formatSoldValue(value){
      const number=asNumber(value);
      return number===null?'—':String(Number(number.toFixed(2)));
    }

    function buildSoldLegHero(payload){
      const soldExplanations=Array.isArray(payload.sold_leg_explanations)?payload.sold_leg_explanations.filter(Boolean):[];
      const fallbackLosses=(payload.legs||[]).filter((item)=>item.result==='loss').map((item)=>({
        leg_label:item.leg||'—',
        target_line:item.line,
        final_value:item.actual_value,
        miss_by:(asNumber(item.line)!==null&&asNumber(item.actual_value)!==null)?Math.abs(asNumber(item.line)-asNumber(item.actual_value)):null,
        short_reason:null,
        last_relevant_context:null,
      }));
      const losses=soldExplanations.length?soldExplanations:fallbackLosses;
      if(!losses.length||payload.parlay_result!=='lost'){
        return '';
      }
      const primary=losses[0]||{};
      const label=primary.player_or_team||primary.leg_label||primary.short_reason||'Losing leg';
      const target=formatSoldValue(primary.target_line);
      const finalValue=formatSoldValue(primary.final_value);
      const missBy=formatSoldValue(Math.abs(asNumber(primary.miss_by)||0));
      const context=primary.last_relevant_context?`<div class='sold-context'><strong>Last relevant context:</strong> ${escapeHtml(primary.last_relevant_context)}</div>`:'';
      const killMomentMeta=(primary.last_relevant_period&&primary.last_relevant_clock)
        ?`<div class='sold-kill-meta'>${escapeHtml(String(primary.last_relevant_clock))} left in ${escapeHtml(String(primary.last_relevant_period))}</div>`
        :'';
      const killMoment=(primary.kill_moment_supported===true&&primary.kill_moment_summary)
        ?`<div class='sold-kill-moment'><div class='sold-kill-title'>Kill moment</div><div class='sold-kill-body'>${escapeHtml(String(primary.kill_moment_summary))}</div>${killMomentMeta}</div>`
        :'';
      const market=primary.market_type||primary.market||'';
      const game=primary.event_name||primary.matched_event||'';
      const summary=(target!=='—'&&finalValue!=='—')
        ?`<strong>${escapeHtml(label)}</strong>${market?` — ${escapeHtml(String(market))}`:''}<br>Final: <strong>${finalValue}</strong><br>Missed by: <strong>${missBy}</strong>${game?`<br>Game: ${escapeHtml(String(game))}`:''}`
        :(primary.short_reason?escapeHtml(primary.short_reason):'This leg sold the slip.');
      const hasMeta=target!=='—'||finalValue!=='—'||missBy!=='—';
      const primaryMeta=hasMeta?`<div class='sold-meta-grid'>
        <div class='sold-meta-item'><div class='sold-meta-label'>Final value</div><div class='sold-meta-value'>${finalValue}</div></div>
        <div class='sold-meta-item'><div class='sold-meta-label'>Target line</div><div class='sold-meta-value'>${target}</div></div>
        <div class='sold-meta-item'><div class='sold-meta-label'>Missed by</div><div class='sold-meta-value'>${missBy}</div></div>
      </div>`:'';

      let others='';
      if(losses.length>1){
        const otherRows=losses.slice(1).map((item)=>{
          const otherLabel=escapeHtml(item.player_or_team||item.leg_label||item.short_reason||'Losing leg');
          const otherFinal=formatSoldValue(item.final_value);
          const otherMiss=formatSoldValue(Math.abs(asNumber(item.miss_by)||0));
          const otherContext=item.last_relevant_context?`<div style='margin-top:4px;opacity:.9;'>Last relevant context: ${escapeHtml(item.last_relevant_context)}</div>`:'';
          return `<div class='sold-other-item'><strong>${otherLabel}</strong><div style='margin-top:3px;'>Finished with ${otherFinal}, missed by ${otherMiss}</div>${otherContext}</div>`;
        }).join('');
        others=`<details class='sold-other-legs'><summary>View ${losses.length-1} other losing leg${losses.length-1===1?'':'s'}</summary><div class='sold-other-list'>${otherRows}</div></details>`;
      }

      return `<div class='sold-hero'>
        <div class='sold-hero-head'>
          <div>
            <div class='sold-kicker'>❌ SOLD THIS SLIP</div>
            <div class='sold-title'>Sold this slip</div>
          </div>
        </div>
        <div class='sold-hero-leg'>${escapeHtml(label)}</div>
        <div class='sold-summary'>${summary}</div>
        ${primaryMeta}
        ${context}
        ${killMoment}
        ${others}
      </div>`;
    }

    function formatMissLegValue(missLeg){
      if(!missLeg){return '—';}
      if(typeof missLeg==='string'){return escapeHtml(missLeg);}
      const label=missLeg.player_or_team||missLeg.leg||'—';
      const delta=missLeg.delta_display?` (${escapeHtml(String(missLeg.delta_display))})`:'';
      return `${escapeHtml(String(label))}${delta}`;
    }

    function buildParlayCloseness(payload){
      if(payload.parlay_closeness_score===undefined||payload.parlay_closeness_score===null){
        return '';
      }
      const closenessScore=Math.round(Number(payload.parlay_closeness_score));
      return `<div class='closeness-card'>
        <div class='closeness-title'>How close was this parlay?</div>
        <div class='closeness-copy'>Your parlay was ${closenessScore}% of the way to hitting.</div>
        <div class='closeness-meta'>
          <div><strong>Closest miss:</strong> ${formatMissLegValue(payload.closest_miss_leg)}</div>
          <div><strong>Worst miss:</strong> ${formatMissLegValue(payload.worst_miss_leg)}</div>
        </div>
      </div>`;
    }

    function renderResultSummary(payload){
      const counts=countLegResults(payload.legs||[]);
      const firstLoss=(payload.legs||[]).find((item)=>item.result==='loss');
      resultSummary.innerHTML=`
        <span class='result-chip'>${counts.won} ✅ Win</span>
        <span class='result-chip'>${counts.lost} ❌ Loss</span>
        <span class='result-chip'>${counts.review} ⚠️ Review</span>
        <span class='result-chip'>${counts.void} ⭕ Void</span>
      `;
      resultSummary.hidden=false;

      const sportSet=new Set((payload.legs||[]).map((item)=>item.sport).filter(Boolean));
      const sports=[...sportSet];
      const betDate=payload.bet_date||payload.slip_default_date||null;
      const hasStake=payload.stake_amount!==undefined&&payload.stake_amount!==null;
      const chips=[];
      if(sports.length===1){chips.push(`<span class='meta-chip'>Sport: ${sports[0]}</span>`);}
      else if(sports.length>1){chips.push(`<span class='meta-chip'>Sport: ${sports.join('/')}</span>`);}
      if(betDate){chips.push(`<span class='meta-chip'>Bet date: ${betDate}</span>`);}
      if(hasStake){chips.push(`<span class='meta-chip'>Stake: $${Number(payload.stake_amount).toFixed(2)}</span>`);}
      if(payload.estimated_payout!==undefined&&payload.estimated_payout!==null){chips.push(`<span class='meta-chip'>Est. payout: $${Number(payload.estimated_payout).toFixed(2)}</span>`);}
      if(hasStake&&payload.payout_message){chips.push(`<span class='meta-chip'>${payload.payout_message}</span>`);}
      const graded=counts.won+counts.lost;
      let secondary='';
      if(counts.lost>0&&counts.review>0){
        secondary=`This slip is already lost. ${counts.review} other leg${counts.review===1?'':'s'} still need review.`;
      }else if(counts.review>0){
        secondary=`${graded} legs resolved · ${counts.review} need review`;
      }else if(counts.void>0){
        secondary=`${counts.won} of ${graded} graded legs hit · ${counts.void} void`;
      }else{
        secondary=`${counts.won} of ${graded} graded legs hit`;
      }
      if(firstLoss&&payload.parlay_result==='lost'){secondary+=` · Sold on ${firstLoss.leg||'a leg'}`;}
      metaSummary.innerHTML=`<span class='meta-chip'>${secondary}</span>${chips.join('')}`;
      metaSummary.hidden=false;
      renderProgressStrip(payload.legs||[]);
      const soldHero=buildSoldLegHero(payload);
      const closenessBlock=buildParlayCloseness(payload);
      if(soldHero){
        diedHere.innerHTML=`${soldHero}${closenessBlock?`<div style='margin-top:10px;'>${closenessBlock}</div>`:''}`;
        diedHere.hidden=false;
        return;
      }
      if(closenessBlock){
        diedHere.innerHTML=closenessBlock;
        diedHere.hidden=false;
        return;
      }
      const reviewMode=payload.parlay_result!=='lost';
      if(counts.review>0||reviewMode){
        const firstReview=(payload.legs||[]).find((item)=>item.result==='review'||item.result==='unmatched');
        if(firstReview){
          diedHere.innerHTML=`<div class='autopsy-card soft'><strong>Parlay autopsy</strong><div style='margin-top:6px;'>Still in review: ${escapeHtml(firstReview.leg||'A leg needs manual review.')}</div><div style='margin-top:2px;font-size:12px;'>Final miss point will appear once unresolved legs are matched.</div></div>`;
          diedHere.hidden=false;
        }
      }
    }

    function escapeHtml(text){
      return String(text||'').replace(/[&<>"]/g,(ch)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]||ch));
    }

    function applyNameSuggestion(legIndex){
      const suggestion=latestPlayerSuggestions.find((item)=>item.legIndex===legIndex);
      if(!suggestion){return;}
      const lines=slip.value.split('\\n');
      if(!lines[legIndex]){return;}
      lines[legIndex]=lines[legIndex].replace(suggestion.fromName,suggestion.toName);
      slip.value=lines.join('\\n');
      latestPlayerSuggestions=latestPlayerSuggestions.filter((item)=>item.legIndex!==legIndex);
      renderNameSuggestions();
    }

    function renderNameSuggestions(){
      if(!latestPlayerSuggestions.length){
        nameSuggestions.style.display='none';
        nameSuggestions.innerHTML='';
        return;
      }
      const rows=latestPlayerSuggestions.map((item)=>`<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;"><div><strong>Did you mean ${escapeHtml(item.toName)}?</strong><div style="font-size:12px;color:#475569;">Parsed as <code>${escapeHtml(item.fromName)}</code> (${item.confidenceLevel} confidence)</div></div><button type="button" class="secondary" data-apply-leg="${item.legIndex}">Apply</button></div>`).join('');
      nameSuggestions.innerHTML=`<div style="font-size:13px;color:#334155;margin-bottom:8px;">Player name suggestions</div>${rows}`;
      nameSuggestions.style.display='block';
      nameSuggestions.querySelectorAll('[data-apply-leg]').forEach((btn)=>{
        btn.addEventListener('click',()=>applyNameSuggestion(Number(btn.getAttribute('data-apply-leg'))));
      });
    }

    function collectPlayerNameSuggestions(parsedLegObjects){
      latestPlayerSuggestions=[];
      parsedLegObjects.forEach((leg,idx)=>{
        if(!leg||!leg.suggested_player_name){return;}
        if(leg.suggestion_auto_applied){return;}
        const fromName=leg.raw_player_text||leg.player_name;
        if(!fromName||fromName===leg.suggested_player_name){return;}
        latestPlayerSuggestions.push({
          legIndex:idx,
          fromName,
          toName:leg.suggested_player_name,
          confidenceLevel:leg.suggestion_confidence_level||'MEDIUM',
        });
      });
      renderNameSuggestions();
    }

    function normalizeScreenshotPayload(body){
      const parsedFromScreenshot=body.parsed_screenshot||{};
      const parsedLegObjects=parsedFromScreenshot.parsed_legs||[];
      const parsedLegs=parsedLegObjects.map((item)=>item.normalized_label||item.raw_leg_text||'—');
      const allReview=parsedLegs.length>0&&(body.result?.legs||[]).every((item)=>item.settlement==='unmatched');
      const extracted=(body.extracted_text||'').trim();
      const parseWarnings=parsedFromScreenshot.parse_warnings||[];
      const parseConfidence=parsedFromScreenshot.confidence||'low';
      const parseWarning=parseWarnings.length
        ?parseWarnings.join(' | ')
        :(parsedLegs.length===0
          ?(extracted
            ?'OCR text was extracted but it was not parseable into bet legs. Try a clearer screenshot.'
            :'No valid betting legs detected.')
          :null);
      return {
        ok:true,
        extracted_text:body.extracted_text||'',
        parsed_legs:parsedLegs,
        parsed_leg_objects:parsedLegObjects,
        detected_bet_date:parsedFromScreenshot.detected_bet_date||null,
        parse_warning:parseWarning,
        parse_confidence:parseConfidence,
        grading_warning:allReview?'Parsed legs were detected, but ESPN matching could not settle any leg.':null,
        sold_leg_explanations:(body.result?.sold_leg_explanations||[]),
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
          resolved_player_id:item.resolved_player_id||item.leg?.resolved_player_id||null,
          parsed_player_name:item.parsed_player_name||item.leg?.parsed_player_name||null,
          normalized_stat_type:item.normalized_stat_type||item.leg?.normalized_stat_type||null,
          resolution_confidence:item.resolution_confidence||item.leg?.resolution_confidence||null,
          parse_confidence:item.parse_confidence||item.leg?.parse_confidence||null,
          matched_boxscore_player_name:item.matched_boxscore_player_name||null,
          selected_bet_date:item.selected_bet_date||item.leg?.selected_bet_date||null,
          player_found_in_boxscore:item.player_found_in_boxscore,
          notes:item.notes||item.leg?.notes||[],
          validation_warnings:item.validation_warnings||[],
          identity_match_method:item.identity_match_method||item.leg?.identity_match_method||null,
          identity_match_confidence:item.identity_match_confidence||item.leg?.identity_match_confidence||null,
          matched_player:item.settlement_explanation?.matched_player||item.resolved_player_name||item.leg?.resolved_player_name||null,
          matched_team:item.settlement_explanation?.matched_team||item.resolved_team||item.leg?.resolved_team||null,
          matched_event_explained:item.settlement_explanation?.matched_event||item.matched_event||item.leg?.event_label||null,
          normalized_market_explained:item.settlement_explanation?.normalized_market||item.normalized_market||null,
          stat_field_used:item.settlement_explanation?.stat_field_used||null,
          selection:item.settlement_explanation?.selection||null,
          normalized_selection:item.settlement_explanation?.normalized_selection||null,
          settlement_reason_code:item.settlement_explanation?.settlement_reason_code||null,
          settlement_reason_text:item.settlement_explanation?.settlement_reason_text||item.settlement_explanation?.settlement_reason||null,
          settlement_reason:item.settlement_explanation?.settlement_reason||null,
          grading_confidence:item.settlement_explanation?.grading_confidence||null,
        })),
        parlay_result:(body.result?.overall==='pending'?'still_live':(body.result?.overall||'needs_review')),
      };
    }

    function renderAnalyzeResult(payload){
      const slipLabel=String(payload.slip_risk_label||'medium').toLowerCase();
      const score=Number(payload.slip_risk_score||0).toFixed(1);
      overall.className=slipLabel==='high'?'loss':(slipLabel==='low'?'win':'review');
      overall.textContent=`🧠 Slip risk: ${slipLabel.toUpperCase()} (${score}/10)`;

      const weakest=payload.weakest_leg;
      const safest=payload.safest_leg;
      const seller=payload.likely_seller;
      resultSummary.innerHTML=`
        <span class='result-chip'>Weakest leg: ${escapeHtml(weakest?.subject_name||weakest?.raw_leg_text||'—')}</span>
        <span class='result-chip'>Safest leg: ${escapeHtml(safest?.subject_name||safest?.raw_leg_text||'—')}</span>
        <span class='result-chip'>Most likely seller: ${escapeHtml(seller?.subject_name||seller?.raw_leg_text||'—')}</span>
      `;
      resultSummary.hidden=false;

      metaSummary.innerHTML=`
        <span class='meta-chip'>Supported legs: ${Number(payload.supported_leg_count||0)}</span>
        <span class='meta-chip'>Unsupported legs: ${Number(payload.unsupported_leg_count||0)}</span>
        <span class='meta-chip'>Advisory only — not a guarantee</span>
      `;
      metaSummary.hidden=false;
      legProgressStrip.hidden=true;
      diedHere.innerHTML="<div class='advisory-banner'>Advisory only — not a guarantee. Use this pre-game read as guidance, not settlement.</div>";
      diedHere.hidden=false;
      payoutOut.textContent='';
      debugOut.innerHTML='';

      legsBody.innerHTML='';
      for(const item of (payload.leg_risk_scores||[])){
        const tr=document.createElement('tr');
        const legCell=document.createElement('td');
        const riskCell=document.createElement('td');
        const advisoryCell=document.createElement('td');

        legCell.innerHTML=`<div style="font-weight:800;">${escapeHtml(item.raw_leg_text||'—')}</div><div style="margin-top:4px;font-size:12px;color:var(--muted);">${escapeHtml(item.market_type||'unknown')}</div>`;
        riskCell.innerHTML=`<span class='risk-chip ${escapeHtml((item.risk_label||'medium').toLowerCase())}'>${escapeHtml(item.risk_label||'medium')}</span><div style='margin-top:6px;font-size:12px;color:var(--muted);'>Score: ${Number(item.risk_score||0).toFixed(1)}/10 · Confidence: ${Number(item.confidence||0).toFixed(2)}</div>`;
        const reasons=Array.isArray(item.advisory_reason_codes)&&item.advisory_reason_codes.length?`<div style='margin-top:6px;font-size:11px;color:var(--muted);'>${item.advisory_reason_codes.map((code)=>escapeHtml(code)).join(' · ')}</div>`:'';
        advisoryCell.innerHTML=`<div class='risk-card'>${escapeHtml(item.explanation||'')}</div>${reasons}`;

        tr.append(legCell,riskCell,advisoryCell);
        legsBody.appendChild(tr);
      }
      wrap.hidden=false;
      msg.textContent='Analyze Slip complete. Advisory only — not a guarantee.';
    }


    function resetRenderedSlipResult(){
      legsBody.innerHTML='';
      debugOut.innerHTML='';
      resultSummary.innerHTML='';
      resultSummary.hidden=true;
      legProgressStrip.hidden=true;
      legProgressStrip.innerHTML='';
      metaSummary.innerHTML='';
      metaSummary.hidden=true;
      diedHere.hidden=true;
      diedHere.innerHTML='';
      summaryOut.value='';
      copyBtn.disabled=true;
      copyLinkBtn.disabled=true;
      openLinkBtn.disabled=true;
      downloadCardBtn.disabled=true;
      latestPublicUrl='';
      latestResultPayload=null;
      clearActionStatus();
      overall.className='review';
      overall.textContent='⚠️ NEEDS REVIEW';
      payoutOut.textContent='';
      gradingSkeleton.classList.remove('show');
    }

    async function submitCheck(){
      const text=slip.value.trim();
      const file=slipImage.files&&slipImage.files[0];
      const screenshotSignature=getScreenshotSignature(file);
      const shouldParseScreenshot=Boolean(file)&&screenshotNeedsParse;
      if(activeSlipMode===modeAnalyze){
        resetRenderedSlipResult();
        wrap.hidden=true;
        if(!text){
          msg.textContent=emptyTextMessage;
          return;
        }
        btn.disabled=true;
        btn.innerHTML="<span class='spinner'></span>Analyzing your slip...";
        msg.textContent='Running deterministic pre-game risk heuristics...';
        try{
          const res=await fetch('/analyze-slip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
          const data=await res.json();
          if(!res.ok){msg.textContent=data.detail||data.message||'Could not analyze this slip right now.';return;}
          renderAnalyzeResult(data);
        }catch(err){
          console.error('Analyze Slip request failed:', err);
          msg.textContent='Could not analyze this slip right now.';
        }finally{
          btn.disabled=false;
          btn.textContent='Analyze Slip';
        }
        return;
      }
      if(!text&&!file){
        resetRenderedSlipResult();
        msg.textContent='Paste at least one leg first, or upload a screenshot.';
        return;
      }
      if(shouldParseScreenshot&&file.type&&!file.type.startsWith('image/')){msg.textContent='Please upload an image file for screenshot grading.';return;}
      if(shouldParseScreenshot&&file.size>8*1024*1024){msg.textContent='Screenshot is too large. Please use an image under 8MB.';return;}

      btn.disabled=true;
      btn.innerHTML="<span class='spinner'></span>Checking your slip...";
      msg.textContent='Parsing slip… Matching players… Finding games… Grading results…';
      gradingSkeleton.classList.add('show');
      try{
        let data;
        let res;
        if(shouldParseScreenshot){
          setScreenshotUploadBusy(true);
          resetManualSelectionState();
          const form=new FormData();
          form.append('file',file);
          res=await fetch('/ingest/screenshot/parse',{method:'POST',body:form});
          const body=await res.json();
          if(!res.ok){msg.textContent=body.detail||body.message||'Could not parse this screenshot right now.';return;}
          const parsed=body.parsed_screenshot||{};
          const parsedLegObjects=parsed.parsed_legs||[];
          const parsedLegs=parsedLegObjects.map((item)=>item.normalized_label||item.raw_leg_text).filter(Boolean);
          collectPlayerNameSuggestions(parsedLegObjects);
          const existingSlipText=slip.value.trim();
          if(parsedLegs.length){
            slip.value=parsedLegs.join('\\n');
            slip.dispatchEvent(new Event('input',{bubbles:true}));
          }else if(body.cleaned_text&&!existingSlipText){
            const cleanedLines=String(body.cleaned_text).split(/\\r?\\n/).map((line)=>line.trim()).filter(Boolean);
            slip.value=cleanedLines.join('\\n');
            slip.dispatchEvent(new Event('input',{bubbles:true}));
          }
          if(!slipDate.value&&parsed.detected_bet_date){slipDate.value=parsed.detected_bet_date;}
          screenshotNeedsParse=false;
          parsedScreenshotSignature=screenshotSignature;
          resetScreenshotInputValue();
          msg.textContent=parsedLegs.length?'Screenshot parsed. Review/edit the text, then click Check Slip.':'Screenshot parsed with limited confidence. Existing text was preserved for safety.';
          removeScreenshotBtn.style.display='inline-block';
          wrap.hidden=true;
          gradingSkeleton.classList.remove('show');
          return;
        }else{
          clearScreenshotSelection({keepMessage:true});
          latestPlayerSuggestions=[];
          renderNameSuggestions();
          const stakeRaw=(stakeAmount.value||'').trim();
          const payload={text};
          if(stakeRaw){payload.stake_amount=stakeRaw;}
          if(slipDate.value){payload.bet_date=slipDate.value; payload.date_of_slip=slipDate.value;}
          if(searchHistorical.checked){payload.search_historical=true;}
          if(Object.keys(selectedGameByLegId).length){payload.selected_event_by_leg_id=selectedGameByLegId;}
          if(Object.keys(selectedPlayerByLegId).length){payload.selected_player_by_leg_id=selectedPlayerByLegId;}
          res=await fetch('/check-slip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          data=await res.json();
        }

        if(!res.ok){msg.textContent=data.detail||data.message||'Could not check this slip right now.';return;}
        msg.textContent=data.message||'Done.';
        resetRenderedSlipResult();
        const overallState=overallTone[data.parlay_result]||'review';
        const overallIcon=overallState==='win'?'✅':(overallState==='loss'?'❌':'⚠️');
        overall.className=overallState;
        overall.textContent=`${overallIcon} ${(overallLabel[data.parlay_result]||'NEEDS REVIEW')}`;
        renderResultSummary(data);
        if(data.estimated_payout!==undefined&&data.estimated_profit!==undefined){
          payoutOut.textContent=`Estimated payout: $${Number(data.estimated_payout).toFixed(2)} (profit: $${Number(data.estimated_profit).toFixed(2)})`;
        }else if(data.payout_message){
          payoutOut.textContent=data.payout_message;
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
          <div><strong>Parsed legs before grading:</strong> ${parsedLegs.length?parsedLegs.join(' | '):'No valid betting legs detected.'}</div>
          <div><strong>Parser confidence:</strong> ${(data.parse_confidence||'low')}</div>
          ${parseWarning}
          ${gradingWarning}
        `;
        summaryOut.value=buildSummary(data);
        latestPublicUrl=data.public_url||'';
        latestResultPayload=data;
        copyBtn.disabled=false;
        copyLinkBtn.disabled=!latestPublicUrl;
        openLinkBtn.disabled=!latestPublicUrl;
        downloadCardBtn.disabled=false;
        wrap.hidden=false;
        gradingSkeleton.classList.remove('show');
      }catch(err){
        console.error('Check Slip request failed:', err);
        msg.textContent='Could not check this slip right now.';
        gradingSkeleton.classList.remove('show');
      }finally{
        setScreenshotUploadBusy(false);
        btn.disabled=false;
        btn.textContent=activeSlipMode===modeAnalyze?'Analyze Slip':'Check Slip';
      }
    }

    form.addEventListener('submit',async(event)=>{
      event.preventDefault();
      await submitCheck();
    });
    btn.addEventListener('click',async()=>{
      await submitCheck();
    });

    window.addEventListener('error',(event)=>{
      console.error('Check page runtime error:', event.error||event.message||event);
      msg.textContent='Something went wrong in the page. Please refresh and try again.';
    });


    function drawShareCard(payload){
      const ctx=shareCardCanvas.getContext('2d');
      if(!ctx){ throw new Error('Share card canvas unavailable.'); }
      const maxLegsOnCard=8;
      const allLegs=Array.isArray(payload.legs)?payload.legs:[];
      const shownLegs=allLegs.slice(0,maxLegsOnCard);
      const hiddenCount=Math.max(0,allLegs.length-shownLegs.length);
      // drawWrappedLine(`+${hiddenCount} more legs`)
      const w=shareCardCanvas.width,h=shareCardCanvas.height,pad=56;
      ctx.fillStyle='#0b1220'; ctx.fillRect(0,0,w,h);
      ctx.fillStyle='#e2e8f0'; ctx.font='bold 54px Arial';
      const isLost=payload.parlay_result==='lost';
      ctx.fillText(`${isLost?'❌':'✅'} ${isLost?'PARLAY SOLD':'PARLAY CHECKED'}`,pad,100);
      const sold=(payload.sold_leg_explanations||[])[0]||((payload.legs||[]).find(l=>l.result==='loss')||null);
      ctx.font='bold 42px Arial'; ctx.fillStyle='#f8fafc';
      let y=170;
      if(sold){
        const soldLabel=sold.player_or_team||sold.leg||sold.leg_label||'Losing leg';
        y+=40; ctx.fillText(String(soldLabel).slice(0,42),pad,y);
        ctx.font='30px Arial'; y+=46;
        const market=sold.market_type||sold.market||'';
        if(market){ctx.fillText(String(market).slice(0,58),pad,y); y+=40;}
        const fv=(sold.final_value??sold.actual_value??'—');
        ctx.fillText(`Final: ${fv}`,pad,y); y+=40;
      }
      ctx.font='bold 34px Arial'; ctx.fillText('Other legs:',pad,y+20); y+=70;
      ctx.font='28px Arial';
      const others=shownLegs.filter(l=>!sold||l.leg!==sold.leg);
      for(const leg of others){
        ctx.fillText(`${resultEmoji[leg.result]||'🧐'} ${String(leg.leg||'—').slice(0,52)}`,pad,y);
        y+=42;
      }
      
      if(hiddenCount>shownLegs.length){ctx.fillStyle='#94a3b8';ctx.font='24px Arial';ctx.fillText(`+${hiddenCount-shownLegs.length} more legs`,pad,h-90);}
      ctx.fillStyle='#93c5fd'; ctx.font='bold 30px Arial';
      ctx.fillText('Checked on ParlayBot',pad,h-50);
    }

    refreshRecentBtn.addEventListener('click',()=>{loadRecentSlips();});
    initTheme();
    initSlipMode();
    loadRecentSlips();

    copyLinkBtn.addEventListener('click',async()=>{
      if(!latestPublicUrl){
        showActionStatus('No public link is available for this result.','error');
        return;
      }
      const full=window.location.origin+latestPublicUrl;
      try{
        await navigator.clipboard.writeText(full);
        showActionStatus('Public link copied.','success');
      }catch(err){
        showActionStatus(`Unable to copy automatically. Public URL: ${full}`,'error');
      }
    });
    openLinkBtn.addEventListener('click',()=>{
      if(!latestPublicUrl){return;}
      window.open(latestPublicUrl,'_blank','noopener');
    });
    downloadCardBtn.addEventListener('click',()=>{
      if(!latestResultPayload){
        showActionStatus('Run a slip check before exporting a share card.','error');
        return;
      }
      try{
        drawShareCard(latestResultPayload);
        const a=document.createElement('a');
        a.href=shareCardCanvas.toDataURL('image/png');
        a.download='parlaybot-share-card.png';
        a.click();
        showActionStatus('Share card downloaded.','success');
      }catch(err){
        console.error('Share card export failed:',err);
        showActionStatus('Could not generate share card image. Please try again.','error');
      }
    });

    copyBtn.addEventListener('click',async()=>{
      const text=summaryOut.value.trim();
      if(!text){
        showActionStatus('No summary available yet.','error');
        return;
      }
      try{
        await navigator.clipboard.writeText(text);
        showActionStatus('Summary copied.','success');
      }catch(err){
        summaryOut.focus();
        summaryOut.select();
        showActionStatus('Copy blocked. Summary selected for manual copy.','error');
      }
    });
  </script>
</body>
</html>'''
    tracker = _ensure_tracker_key(tracker_key)
    response = HTMLResponse(html)
    if tracker != _normalize_tracker_key(tracker_key):
        response.set_cookie(key=_TRACKER_COOKIE_NAME, value=tracker, httponly=False, max_age=60 * 60 * 24 * 365, samesite='lax')
    return response


def _estimate_profit_from_american(stake_amount: float, american_odds: int) -> float:
    if american_odds > 0:
        return round(stake_amount * (american_odds / 100.0), 2)
    return round(stake_amount * (100.0 / abs(american_odds)), 2)


def _american_to_decimal(american_odds: int) -> float:
    if american_odds > 0:
        return (american_odds / 100.0) + 1.0
    return (100.0 / abs(american_odds)) + 1.0


def _estimate_parlay_payout_from_leg_odds(stake_amount: float, american_odds_list: list[int]) -> tuple[float, float, float]:
    decimal_total = 1.0
    for american_odds in american_odds_list:
        decimal_total *= _american_to_decimal(american_odds)
    payout = round(stake_amount * decimal_total, 2)
    profit = round(payout - stake_amount, 2)
    return round(decimal_total, 4), payout, profit


def _player_resolution_method(match_method: str | None, result: str) -> str:
    method = (match_method or '').strip().lower()
    if method in {'canonical', 'alias', 'normalized'}:
        return 'exact'
    if method == 'single_token_shorthand':
        return 'surname_shorthand'
    if method in {'single_token_first_name', 'single_token_first_name_heuristic'}:
        return 'first_name_shorthand'
    if method == 'single_strong_candidate':
        return 'single_strong_candidate'
    if method in {'fuzzy'}:
        return 'fuzzy'
    if method in {'ambiguous'} or result == 'review':
        return 'manual_review'
    return 'exact'


def _player_resolution_status(item: GradedLeg, *, method: str) -> str:
    has_player = bool(item.leg.player)
    has_resolved_player = bool(item.resolved_player_name or item.leg.resolved_player_name)
    if not has_player:
        return 'exact'
    if has_resolved_player and method == 'exact':
        return 'exact'
    if has_resolved_player and method in {'surname_shorthand', 'first_name_shorthand', 'single_strong_candidate', 'fuzzy'}:
        return 'fuzzy_resolved'
    if method == 'manual_review' or (item.identity_match_confidence or item.leg.identity_match_confidence) == 'LOW':
        return 'ambiguous'
    return 'unresolved'


def _player_resolution_confidence(item: GradedLeg) -> str | float | None:
    confidence_tier = item.identity_match_confidence or item.leg.identity_match_confidence
    if confidence_tier:
        return confidence_tier.lower()
    numeric_conf = item.resolution_confidence if item.resolution_confidence is not None else item.leg.resolution_confidence
    if numeric_conf is None:
        return None
    return round(float(numeric_conf), 2)


def _player_resolution_explanation(item: GradedLeg, *, status: str, method: str, did_you_mean: str | None) -> str:
    resolved_name = item.resolved_player_name or item.leg.resolved_player_name
    ambiguity_reason = item.resolution_ambiguity_reason or item.leg.resolution_ambiguity_reason
    review_reason = item.review_reason_text or item.review_reason or item.explanation_reason
    if status == 'exact':
        return f'Exact player match: {resolved_name}.' if resolved_name else 'Exact player match.'
    if status == 'fuzzy_resolved':
        if method == 'single_strong_candidate':
            return f'Conservatively resolved to {resolved_name} from a likely player name match.' if resolved_name else 'Conservatively resolved from a likely player name match.'
        return f'Resolved to {resolved_name} using conservative player name matching.' if resolved_name else 'Resolved using conservative player name matching.'
    if ambiguity_reason:
        return ambiguity_reason
    if review_reason:
        return review_reason
    if did_you_mean:
        return 'Player could not be confidently resolved.'
    return 'Needs manual review. We could not confidently resolve this leg.'


def _build_player_resolution_details(item: GradedLeg, *, result: str, did_you_mean: str | None) -> dict[str, object]:
    method = _player_resolution_method(item.identity_match_method or item.leg.identity_match_method, result)
    status = _player_resolution_status(item, method=method)
    details: dict[str, object] = {
        'player_resolution_status': status,
        'player_resolution_method': method,
        'player_resolution_confidence': _player_resolution_confidence(item),
        'player_resolution_explanation': _player_resolution_explanation(item, status=status, method=method, did_you_mean=did_you_mean),
        'player_resolution_is_exact': status == 'exact',
        'player_resolution_is_conservative': status == 'fuzzy_resolved',
        'canonical_matched_player_name': item.canonical_player_name or item.leg.canonical_player_name or item.resolved_player_name or item.leg.resolved_player_name,
        'selected_player_name': item.selected_player_name or item.leg.selected_player_name,
        'selected_player_id': item.selected_player_id or item.leg.selected_player_id,
        'selection_source': item.selection_source or item.leg.selection_source,
        'selection_explanation': item.selection_explanation or item.leg.selection_explanation,
        'original_typed_player_name': item.leg.parsed_player_name or item.leg.player,
    }
    if did_you_mean and status in {'ambiguous', 'unresolved'}:
        details['did_you_mean'] = did_you_mean
    return details




_REVIEW_REASON_TEXT_BY_CODE: dict[str, str] = {
    'PLAYER_AMBIGUOUS': 'Multiple plausible player matches found; select the correct player.',
    'PLAYER_UNRESOLVED': "We couldn't confidently confirm this player from the slip text.",
    'INVALID_SELECTED_PLAYER_ID': 'Selected player could not be applied; please choose again.',
    'INVALID_SELECTED_EVENT_ID': 'Selected game could not be applied; choose a listed game for this leg.',
    'PLAYER_NOT_ON_EVENT_ROSTER': "We matched the game, but couldn't fully confirm the player for this leg.",
    'EVENT_NOT_FOUND': 'No matching game was found for the resolved team/date.',
    'MULTIPLE_GAMES_MATCHED': 'Multiple possible games were found for this player. Select the correct one.',
    'NEARBY_DATE_CANDIDATES_ONLY': 'Only nearby-date games were found; confirm the correct date.',
    'UNSUPPORTED_MARKET': 'Recognized but not fully supported yet. This market was kept for review instead of being dropped.',
}


def _review_reason_text_from_code(code: str | None, fallback: str | None) -> str:
    if code and code in _REVIEW_REASON_TEXT_BY_CODE:
        return _REVIEW_REASON_TEXT_BY_CODE[code]
    return fallback or 'Needs manual review. We could not confidently resolve this leg.'

def _event_resolution_source(item: GradedLeg) -> str:
    matched_by = (item.leg.matched_by or '').lower()
    if matched_by.startswith('team_'):
        return 'team'
    if matched_by.startswith('player_'):
        if item.leg.player and item.leg.resolved_team:
            return 'merged'
        return 'player'
    if item.leg.player and item.leg.resolved_team and (item.candidate_games or item.leg.event_candidates):
        return 'merged'
    if item.leg.player:
        return 'player'
    if item.leg.team:
        return 'team'
    return 'none'


def _review_reason_code(item: GradedLeg, *, did_you_mean: str | None) -> str | None:
    if item.settlement not in {'unmatched'}:
        return None
    reason_text = ((item.review_reason_text or item.review_reason or item.explanation_reason or '')).lower()
    notes = ' | '.join(item.leg.notes).lower()
    unmatched_reason_code = str((item.settlement_diagnostics or {}).get('unmatched_reason_code') or '').lower()
    settlement_reason_code = str(
        (item.settlement_explanation.settlement_reason_code if item.settlement_explanation else '') or ''
    ).lower()
    identity_method = item.identity_match_method or item.leg.identity_match_method
    identity_confidence = item.identity_match_confidence or item.leg.identity_match_confidence
    if (item.selection_error_code or item.leg.selection_error_code) == 'INVALID_SELECTED_PLAYER_ID':
        return 'INVALID_SELECTED_PLAYER_ID'
    if (item.selection_error_code or item.leg.selection_error_code) == 'INVALID_SELECTED_EVENT_ID':
        return 'INVALID_SELECTED_EVENT_ID'
    if 'player_not_on_event_roster' in unmatched_reason_code or 'player not found on event roster' in reason_text or 'does not include player team' in notes:
        return 'PLAYER_NOT_ON_EVENT_ROSTER'
    if identity_method == 'ambiguous' or identity_confidence == 'LOW' or 'identity ambiguous' in reason_text:
        return 'PLAYER_AMBIGUOUS'
    if did_you_mean or 'player not found' in reason_text or 'likely refers to' in reason_text:
        return 'PLAYER_UNRESOLVED'
    if (
        unmatched_reason_code == 'unsupported_market'
        or settlement_reason_code == 'unsupported_market'
        or 'unsupported market' in reason_text
        or 'market mapping missing' in reason_text
        or 'special market support is limited' in reason_text
    ):
        return 'UNSUPPORTED_MARKET'
    event_reason_code = (item.event_review_reason_code or item.leg.event_review_reason_code or '').lower()
    if event_reason_code == 'nearby_date_candidates_only':
        return 'NEARBY_DATE_CANDIDATES_ONLY'
    if event_reason_code in {'multiple_plausible_events'}:
        return 'MULTIPLE_GAMES_MATCHED'
    if len(item.candidate_games or item.candidate_events or item.leg.event_candidates) > 1 or 'multiple possible games' in notes:
        return 'MULTIPLE_GAMES_MATCHED'
    if 'no game found for resolved team on date' in notes or unmatched_reason_code in {'event_unresolved', 'no_candidate_events'}:
        return 'EVENT_NOT_FOUND'
    if 'parse stat type' in reason_text or 'parse stat type' in notes:
        return 'STAT_TYPE_UNCLEAR'
    if 'event unresolved' in reason_text or 'no candidate events' in reason_text or 'no_candidate_events' in str(item.settlement_diagnostics):
        return 'EVENT_NOT_FOUND'
    return 'PARTIAL_SLIP_REVIEW'


def _candidate_players_payload(item: GradedLeg) -> list[dict[str, object | None]]:
    detail_candidates = item.candidate_player_details or item.leg.candidate_player_details
    if detail_candidates:
        return [
            {
                'player_name': str(candidate.get('player_name') or ''),
                'team_name': candidate.get('team_name'),
                'player_id': candidate.get('player_id'),
                'match_confidence': candidate.get('match_confidence'),
                'rank': candidate.get('rank') or (idx + 1),
                'reason': candidate.get('reason'),
            }
            for idx, candidate in enumerate(detail_candidates)
            if isinstance(candidate, dict) and str(candidate.get('player_name') or '').strip()
        ]

    names = item.candidate_players or item.leg.candidate_players
    return [
        {
            'player_name': name,
            'team_name': None,
            'player_id': None,
            'match_confidence': None,
            'rank': idx + 1,
            'reason': None,
        }
        for idx, name in enumerate(names)
        if str(name).strip()
    ]


def _build_review_details(item: GradedLeg, *, result: str, did_you_mean: str | None) -> dict[str, object] | None:
    if result != 'review':
        return None
    player_resolution_details = _build_player_resolution_details(item, result=result, did_you_mean=did_you_mean)
    candidate_players = _candidate_players_payload(item)
    matched_event_count = 1 if (item.matched_event or item.leg.event_label) else 0

    reason_code = _review_reason_code(item, did_you_mean=did_you_mean) or 'PARTIAL_SLIP_REVIEW'
    fallback_reason = item.event_review_reason_text or item.leg.event_review_reason_text or item.review_reason_text or item.review_reason or item.explanation_reason
    reason_text = _review_reason_text_from_code(reason_code, fallback_reason)
    details: dict[str, object] = {
        **player_resolution_details,
        'candidate_count': len(candidate_players),
        'matched_event_count': matched_event_count,
        'event_resolution_source': _event_resolution_source(item),
        'review_reason_code': reason_code,
        'review_reason_text': reason_text,
    }
    if did_you_mean:
        details['did_you_mean'] = did_you_mean
    return details


def _override_grading_explanation(item: GradedLeg, *, result: str) -> str | None:
    override_used = bool(item.override_used_for_grading or item.leg.override_used_for_grading)
    player_applied = bool(item.selection_applied or item.leg.selection_applied)
    event_applied = bool(item.event_selection_applied or item.leg.event_selection_applied)
    player_selected = bool(player_applied or (item.selection_source or item.leg.selection_source) == 'user_selected' or (item.selected_player_id or item.leg.selected_player_id))
    event_selected = bool(event_applied or (item.event_selection_source or item.leg.event_selection_source) == 'user_selected' or (item.selected_event_id or item.leg.selected_event_id))

    if player_applied and event_applied:
        return 'Used selected player and selected game for grading.'
    if player_applied and event_selected and not event_applied:
        return 'Used selected player for grading, but selected game could not be applied.'
    if event_applied and player_selected and not player_applied:
        return 'Used selected game for grading, but player selection was not applied.'
    if event_applied:
        return 'Used selected game for grading.'
    if player_applied:
        return 'Used selected player for grading.'

    if override_used:
        return 'Manual selection used for grading.'

    if player_selected and event_selected:
        return 'Selected player and game were recorded, but could not both be applied for final grading.'
    if event_selected:
        return 'Selected game could not be applied.' if (item.selection_error_code or item.leg.selection_error_code) == 'INVALID_SELECTED_EVENT_ID' else 'Selected game was recorded, but final grading still used auto-matched event.'
    if player_selected:
        return 'Selected player could not be applied.' if (item.selection_error_code or item.leg.selection_error_code) == 'INVALID_SELECTED_PLAYER_ID' else 'Selected player was recorded, but final grading still used auto-matched player.'
    return None


def _override_grading_explanation_from_public_leg(leg: dict[str, object]) -> str | None:
    player_applied = bool(leg.get('player_selection_applied') or leg.get('selection_applied'))
    event_applied = bool(leg.get('event_selection_applied'))
    override_used = bool(leg.get('override_used_for_grading'))
    player_selected = bool(player_applied or leg.get('selected_player_id') or leg.get('selected_player_name'))
    event_selected = bool(event_applied or leg.get('selected_event_id') or leg.get('selected_event_label'))

    if player_applied and event_applied:
        return 'Used selected player and selected game for grading.'
    if player_applied and event_selected and not event_applied:
        return 'Used selected player for grading, but selected game could not be applied.'
    if event_applied and player_selected and not player_applied:
        return 'Used selected game for grading, but player selection was not applied.'
    if event_applied:
        return 'Used selected game for grading.'
    if player_applied:
        return 'Used selected player for grading.'
    if override_used:
        return 'Manual selection used for grading.'
    if player_selected and event_selected:
        return 'Selected player and game were recorded, but could not both be applied for final grading.'
    if event_selected:
        return 'Selected game was recorded, but final grading still used auto-matched event.'
    if player_selected:
        return 'Selected player was recorded, but final grading still used auto-matched player.'
    return None


def _persistable_public_leg(leg: dict[str, object]) -> dict[str, object]:
    row = dict(leg)
    row['player_selection_applied'] = bool(row.get('player_selection_applied') or row.get('selection_applied'))
    row['event_selection_applied'] = bool(row.get('event_selection_applied'))
    row['override_used_for_grading'] = bool(row.get('override_used_for_grading'))
    row['override_grading_explanation'] = str(
        row.get('override_grading_explanation') or _override_grading_explanation_from_public_leg(row) or ''
    ) or None
    for field in (
        'selected_player_name',
        'selected_player_id',
        'selected_event_id',
        'selected_event_label',
        'selection_source',
        'selection_explanation',
    ):
        value = row.get(field)
        row[field] = str(value).strip() if value is not None and str(value).strip() else None
    return row


def _process_public_check_text(
    text: str,
    stake_amount: float | None = None,
    date_of_slip: date | datetime | None = None,
    bet_date: date | None = None,
    search_historical: bool = False,
    selected_event_id: str | None = None,
    selected_event_by_leg_id: dict[str, str] | None = None,
    selected_player_by_leg_id: dict[str, str] | None = None,
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
            'parse_confidence': 'low',
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
            'parse_confidence': 'low',
        }

    parsed = parse_text(normalized)
    valid_parsed = filter_valid_legs(parsed)
    parsed_legs = [leg.raw_text for leg in valid_parsed]
    if not parsed_legs:
        return {
            'ok': False,
            'message': 'No valid betting legs detected.',
            'legs': [],
            'parsed_legs': [],
            'parse_warning': 'No valid betting legs detected.',
            'grading_warning': None,
            'parlay_result': 'needs_review',
            'parse_confidence': 'low',
        }

    try:
        grade_kwargs: dict[str, object] = {
            'provider': _public_check_provider,
            'posted_at': date_of_slip,
        }
        if bet_date is not None:
            grade_kwargs['bet_date'] = bet_date
        if search_historical:
            grade_kwargs['include_historical'] = True
        if selected_event_id:
            grade_kwargs['selected_event_id'] = selected_event_id
        if selected_event_by_leg_id:
            grade_kwargs['selected_event_by_leg_id'] = selected_event_by_leg_id
        if selected_player_by_leg_id:
            grade_kwargs['selected_player_by_leg_id'] = selected_player_by_leg_id
        grading_text = '\n'.join(parsed_legs)
        graded = _grade_text_with_observability(grading_text, **grade_kwargs)
    except Exception:
        return {
            'ok': False,
            'message': 'Could not grade this slip right now.',
            'legs': [],
            'parsed_legs': parsed_legs,
            'parse_warning': None,
            'grading_warning': 'Parsed legs were detected, but grading did not complete.',
            'parlay_result': 'needs_review',
            'parse_confidence': 'low',
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
        did_you_mean = None
        suggestion_candidates = [c.get('player_name') for c in _candidate_players_payload(item) if c.get('player_name')]
        if result == 'review' and suggestion_candidates:
            did_you_mean = f"Did you mean: {suggestion_candidates[0]}?"

        resolution_details = _build_player_resolution_details(item, result=result, did_you_mean=did_you_mean)
        review_details = _build_review_details(item, result=result, did_you_mean=did_you_mean)
        effective_review_text = (review_details or {}).get('review_reason_text') if isinstance(review_details, dict) else None
        override_grading_explanation = _override_grading_explanation(item, result=result)

        legs.append({
            'leg_id': str(index),
            'leg': item.leg.raw_text,
            'sport': item.leg.sport,
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
            'candidate_players': _candidate_players_payload(item),
            'candidate_events': item.candidate_events or item.candidate_games or item.leg.event_candidates,
            'resolved_player_name': item.resolved_player_name or item.leg.resolved_player_name,
            'resolved_team': item.resolved_team or item.leg.resolved_team,
            'resolved_player_id': item.resolved_player_id or item.leg.resolved_player_id,
            'player_selection_applied': bool(item.selection_applied or item.leg.selection_applied or (item.identity_match_method or item.leg.identity_match_method) == 'manual_selection'),
            'selected_player_name': item.selected_player_name or item.leg.selected_player_name,
            'selected_player_id': item.selected_player_id or item.leg.selected_player_id,
            'selection_source': item.selection_source or item.leg.selection_source,
            'selection_explanation': item.selection_explanation or item.leg.selection_explanation,
            'selection_applied': bool(item.selection_applied or item.leg.selection_applied),
            'selection_error_code': item.selection_error_code or item.leg.selection_error_code,
            'canonical_player_name': item.canonical_player_name or item.leg.canonical_player_name,
            'event_selection_applied': bool(item.event_selection_applied or item.leg.event_selection_applied),
            'selected_event_id': item.selected_event_id or item.leg.selected_event_id,
            'selected_event_label': item.selected_event_label or item.leg.selected_event_label,
            'event_selection_source': item.event_selection_source or item.leg.event_selection_source,
            'event_selection_explanation': item.event_selection_explanation or item.leg.event_selection_explanation,
            'override_used_for_grading': bool(item.override_used_for_grading or item.leg.override_used_for_grading),
            'override_grading_explanation': override_grading_explanation,
            'parsed_player_name': item.parsed_player_name or item.leg.parsed_player_name,
            'normalized_stat_type': item.normalized_stat_type or item.leg.normalized_stat_type,
            'resolution_confidence': item.resolution_confidence or item.leg.resolution_confidence,
            'matched_event_date': item.matched_event_date or item.leg.matched_event_date,
            'matched_team': item.matched_team or item.leg.matched_team,
            'event_resolution_confidence': item.event_resolution_confidence or item.leg.event_resolution_confidence,
            'event_resolution_warnings': item.event_resolution_warnings or item.leg.event_resolution_warnings,
            'event_review_reason_code': item.event_review_reason_code or item.leg.event_review_reason_code,
            'event_review_reason_text': item.event_review_reason_text or item.leg.event_review_reason_text,
            'parse_confidence': item.parse_confidence or item.leg.parse_confidence,
            'matched_boxscore_player_name': item.matched_boxscore_player_name,
            'selected_bet_date': item.selected_bet_date or item.leg.selected_bet_date,
            'player_found_in_boxscore': item.player_found_in_boxscore,
            'validation_warnings': item.validation_warnings,
            'notes': item.leg.notes,
            'identity_match_method': item.identity_match_method or item.leg.identity_match_method,
            'identity_match_confidence': item.identity_match_confidence or item.leg.identity_match_confidence,
            'settlement_explanation': item.settlement_explanation.model_dump() if item.settlement_explanation else None,
            'matched_player': item.settlement_explanation.matched_player if item.settlement_explanation else None,
            'matched_team_explained': item.settlement_explanation.matched_team if item.settlement_explanation else None,
            'matched_event_explained': item.settlement_explanation.matched_event if item.settlement_explanation else None,
            'normalized_market_explained': item.settlement_explanation.normalized_market if item.settlement_explanation else None,
            'stat_field_used': item.settlement_explanation.stat_field_used if item.settlement_explanation else None,
            'selection': item.settlement_explanation.selection if item.settlement_explanation else None,
            'normalized_selection': item.settlement_explanation.normalized_selection if item.settlement_explanation else None,
            'settlement_reason_code': item.settlement_explanation.settlement_reason_code if item.settlement_explanation else None,
            'settlement_reason_text': item.settlement_explanation.settlement_reason_text if item.settlement_explanation else None,
            'settlement_reason': item.settlement_explanation.settlement_reason if item.settlement_explanation else None,
            'grading_confidence': item.settlement_explanation.grading_confidence if item.settlement_explanation else None,
            'settlement_diagnostics': item.settlement_diagnostics,
            'unmatched_reason_code': (item.settlement_diagnostics or {}).get('unmatched_reason_code'),
            'review_reason_text': effective_review_text or item.review_reason_text,
            'did_you_mean': did_you_mean,
            'review_details': review_details,
            'resolution_details': resolution_details,
            'player_resolution_status': resolution_details.get('player_resolution_status'),
            'player_resolution_method': resolution_details.get('player_resolution_method'),
            'player_resolution_explanation': resolution_details.get('player_resolution_explanation'),
            'player_resolution_confidence': resolution_details.get('player_resolution_confidence'),
            'debug_comparison': item.debug_comparison,
        })


    slip_default_date = next((item.leg.slip_default_date for item in graded.legs if item.leg.slip_default_date), None)
    mixed_event_dates_detected = any(bool(item.leg.mixed_event_dates_detected) for item in graded.legs)
    parlay_result = 'still_live' if graded.overall == 'pending' else graded.overall
    out = {
        'ok': True,
        'message': 'Slip checked.',
        'legs': legs,
        'parsed_legs': parsed_legs,
        'parse_warning': None,
        'grading_warning': None,
        'parlay_result': parlay_result,
        'slip_default_date': slip_default_date,
        'mixed_event_dates_detected': mixed_event_dates_detected,
        'parse_confidence': next((item.get('parse_confidence') for item in legs if item.get('parse_confidence')), 'low'),
        'checked_at': datetime.utcnow().isoformat(),
        'bet_date': bet_date.isoformat() if bet_date is not None else None,
        'selected_player_by_leg_id': selected_player_by_leg_id or {},
        'sold_leg_explanations': [item.model_dump() for item in (graded.sold_leg_explanations or [])],
        'parlay_closeness_score': graded.parlay_closeness_score,
        'closest_miss_leg': graded.closest_miss_leg,
        'worst_miss_leg': graded.worst_miss_leg,
    }
    if unmatched_count == len(legs):
        out['message'] = 'Parsed legs were detected, but ESPN matching could not settle any leg.'
        out['grading_warning'] = 'Parsed legs were detected, but ESPN matching could not settle any leg.'
    elif unmatched_count > 0:
        out['message'] = f'{unmatched_count} leg(s) need manual review.'
        out['grading_warning'] = f'{unmatched_count} leg(s) need manual review.'

    if ambiguous_count > 0:
        out['grading_warning'] = 'This leg matches multiple possible games. Add opponent/date or upload the full slip.'

    if stake_amount is not None:
        financials = extract_financials(normalized)
        out['stake_amount'] = round(stake_amount, 2)
        leg_odds = [leg.american_odds for leg in valid_parsed if leg.american_odds is not None]
        if len(leg_odds) == len(valid_parsed) and leg_odds:
            decimal_total, est_payout, est_profit = _estimate_parlay_payout_from_leg_odds(stake_amount, leg_odds)
            out['estimated_profit'] = est_profit
            out['estimated_payout'] = est_payout
            out['american_odds_used'] = leg_odds
            out['decimal_odds_used'] = decimal_total
            return out
        if financials.american_odds is None:
            out['payout_message'] = 'Add odds in your slip text (for example +120) to estimate payout.'
            return out
        est_profit = _estimate_profit_from_american(stake_amount, financials.american_odds)
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


def _process_public_analyze_text(text: str) -> AnalyzeSlipResponse:
    normalized = text.strip()
    if not normalized:
        return AnalyzeSlipResponse(
            ok=False,
            message='Paste at least one leg first.',
            slip_risk_score=0.0,
            slip_risk_label='low',
            weakest_leg=None,
            safest_leg=None,
            likely_seller=None,
            leg_risk_scores=[],
            supported_leg_count=0,
            unsupported_leg_count=0,
            advisory_only=True,
        )
    parsed = parse_text(normalized)
    return analyze_slip_risk(parsed)


@app.post('/analyze-slip', response_model=AnalyzeSlipResponse)
def public_analyze_slip(request: Request, response: Response, payload: dict = Body(...)) -> AnalyzeSlipResponse:
    _enforce_public_check_rate_limit(request, response, 'analyze-slip')
    return _process_public_analyze_text(str(payload.get('text', '')))


@app.post('/check')
@app.post('/check-slip')
def public_check_slip(request: Request, response: Response, payload: dict = Body(...), db: Session = Depends(get_db), tracker_key: str | None = Cookie(default=None, alias=_TRACKER_COOKIE_NAME)):
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

    selected_player_payload = payload.get('selected_player_by_leg_id')
    if isinstance(selected_player_payload, dict):
        selected_player_by_leg_id = {str(key): str(value) for key, value in selected_player_payload.items() if str(value).strip()}
    else:
        selected_player_by_leg_id = {}

    resolved_tracker_key = _ensure_tracker_key(_normalize_tracker_key(tracker_key) or _normalize_tracker_key(str(payload.get('tracker_key') or '')))

    result = _process_public_check_text(
        str(payload.get('text', '')),
        stake_amount=parsed_stake,
        date_of_slip=parsed_date,
        bet_date=parsed_date,
        search_historical=bool(payload.get('search_historical', False)),
        selected_event_id=(str(payload.get('selected_event_id') or '').strip() or None),
        selected_event_by_leg_id=selected_event_by_leg_id,
        selected_player_by_leg_id=selected_player_by_leg_id,
    )
    if _has_persistable_public_result(result):
        bet_dt = datetime.combine(parsed_date, datetime.min.time()) if parsed_date else None
        persistable_legs = [
            _persistable_public_leg(leg)
            for leg in result.get('legs', [])
            if isinstance(leg, dict)
        ]
        saved = save_public_slip_result(
            db,
            raw_slip_text=str(payload.get('text', '')).strip(),
            parsed_legs=[str(item) for item in result.get('parsed_legs', [])],
            legs=persistable_legs,
            overall_result=str(result.get('parlay_result', 'needs_review')),
            parser_confidence=result.get('parse_confidence'),
            bet_date=bet_dt,
            stake_amount=parsed_stake,
            tracker_key=resolved_tracker_key,
        )
        result['public_id'] = saved.public_id
        result['public_url'] = f"/r/{saved.public_id}"
        result['tracker_key'] = resolved_tracker_key
    return result



@app.get('/my-slips')
def public_recent_slips_endpoint(db: Session = Depends(get_db), tracker_key: str | None = Cookie(default=None, alias=_TRACKER_COOKIE_NAME)):
    resolved_tracker_key = _normalize_tracker_key(tracker_key)
    if not resolved_tracker_key:
        return {'items': []}
    rows = list_recent_public_slips(db, tracker_key=resolved_tracker_key, limit=12)
    items: list[dict] = []
    for row in rows:
        try:
            legs = json.loads(row.legs_json or '[]')
        except json.JSONDecodeError:
            legs = []
        checked_at = row.checked_at or row.created_at
        checked_at_label = checked_at.strftime('%Y-%m-%d %H:%M') if checked_at else None
        bet_date_label = row.bet_date.date().isoformat() if row.bet_date else None
        preview = row.raw_slip_text.strip().splitlines()[0] if row.raw_slip_text else ''
        items.append({
            'public_id': row.public_id,
            'public_url': f'/r/{row.public_id}',
            'overall_result': row.overall_result,
            'summary': _slip_status_summary(legs if isinstance(legs, list) else []),
            'bet_date': bet_date_label,
            'checked_at_label': checked_at_label,
            'checked_at': checked_at.isoformat() if checked_at else None,
            'stake_amount': row.stake_amount,
            'preview_text': preview[:90],
            'parsed_legs': json.loads(row.parsed_legs_json or '[]'),
            'share_url': f'/r/{row.public_id}',
            'leg_statuses': [str(leg.get('result', 'review')) for leg in legs if isinstance(leg, dict)],
        })
    return {'items': items}


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


@app.get('/r/{public_id}', response_class=HTMLResponse)
@app.get('/parlay/{public_id}', response_class=HTMLResponse)
def public_parlay_result_page(public_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    normalized_public_id = public_id.strip().lower()
    if not _PUBLIC_SLIP_ID_PATTERN.fullmatch(normalized_public_id):
        html = (
            "<!doctype html><html><head><title>ParlayBot Result</title>"
            "<style>body{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:860px;color:#0f172a;}"
            ".card{border:1px solid #e2e8f0;border-radius:12px;padding:18px;background:#fff;}"
            ".notice{margin-top:12px;padding:12px;border-radius:10px;background:#fef2f2;color:#991b1b;border:1px solid #fecaca;}"
            "a{text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:700;display:inline-block;margin-top:16px;}"
            ".cta{background:#0f172a;color:#fff;}</style></head><body>"
            "<h1>ParlayBot Result</h1><div class='card'><h2>We couldn't open that shared slip.</h2>"
            "<div class='notice'>The public ID format is invalid. Please verify the link and try again.</div>"
            "<a class='cta' href='/check'>Check a new slip</a></div></body></html>"
        )
        return HTMLResponse(html, status_code=404)

    row = get_public_slip_result(db, normalized_public_id)
    if not row:
        html = (
            "<!doctype html><html><head><title>ParlayBot Result</title>"
            "<style>body{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:860px;color:#0f172a;}"
            ".card{border:1px solid #e2e8f0;border-radius:12px;padding:18px;background:#fff;}"
            ".notice{margin-top:12px;padding:12px;border-radius:10px;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;}"
            "a{text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:700;display:inline-block;margin-top:16px;}"
            ".cta{background:#0f172a;color:#fff;}</style></head><body>"
            "<h1>ParlayBot Result</h1><div class='card'><h2>This public slip was not found.</h2>"
            "<div class='notice'>It may have expired, been removed, or the link may be incomplete.</div>"
            "<a class='cta' href='/check'>Check a new slip</a></div></body></html>"
        )
        return HTMLResponse(html, status_code=404)

    legs = json.loads(row.legs_json or '[]')
    matched_events = json.loads(row.matched_events_json or '[]')
    checked_at = row.created_at.isoformat() if row.created_at else 'Unknown'
    result_label = {'cashed': 'CASHED', 'lost': 'LOST', 'still_live': 'STILL LIVE', 'needs_review': 'NEEDS REVIEW'}.get(row.overall_result, row.overall_result.upper())
    emoji = {'win': '✅', 'loss': '❌', 'pending': '⏳', 'push': '➖', 'void': '🚫', 'review': '🧐', 'unmatched': '🧐'}
    leg_rows = []
    for leg in legs:
        display_parts = [escape(str(leg.get('leg') or '—'))]
        selected_player = leg.get('selected_player_name')
        selected_game = leg.get('selected_event_label')
        if selected_player:
            display_parts.append(f"<div style='margin-top:4px;color:#334155;'><strong>Selected player:</strong> {escape(str(selected_player))}</div>")
        if selected_game:
            display_parts.append(f"<div style='margin-top:4px;color:#334155;'><strong>Selected game:</strong> {escape(str(selected_game))}</div>")

        reason = leg.get('review_reason_text') or leg.get('review_reason') or leg.get('settlement_reason_text') or '—'
        override_text = leg.get('override_grading_explanation') or _override_grading_explanation_from_public_leg(leg)
        if override_text:
            reason = f"{reason} | {override_text}" if reason != '—' else str(override_text)

        leg_rows.append(
            "<tr>"
            f"<td>{''.join(display_parts)}</td>"
            f"<td>{emoji.get(leg.get('result'), '🧐')} {escape((leg.get('result') or 'review').upper())}</td>"
            f"<td>{escape(str(leg.get('matched_event') or selected_game or '—'))}</td>"
            f"<td>{escape(str(reason))}</td>"
            "</tr>"
        )

    if not leg_rows:
        leg_rows.append("<tr><td colspan='4'>No leg details were available for this shared result.</td></tr>")

    events_html = ''.join(f"<li>{escape(str(event))}</li>" for event in matched_events) or '<li>—</li>'

    sold_leg = next((leg.get('sold_leg_explanation') for leg in legs if isinstance(leg, dict) and isinstance(leg.get('sold_leg_explanation'), dict)), None)
    sold_html = ''
    if row.overall_result == 'lost' and sold_leg:
        sold_label = escape(str(sold_leg.get('player_or_team') or 'Losing leg'))
        sold_market = escape(str(sold_leg.get('market_type') or ''))
        sold_target = escape(str(sold_leg.get('target_line') if sold_leg.get('target_line') is not None else '—'))
        sold_final = escape(str(sold_leg.get('final_value') if sold_leg.get('final_value') is not None else '—'))
        sold_miss = escape(str(sold_leg.get('miss_by') if sold_leg.get('miss_by') is not None else '—'))
        sold_game = escape(str(sold_leg.get('event_name') or sold_leg.get('matched_event') or '—'))
        sold_html = f"<div style='margin:14px 0;padding:12px;border-radius:12px;border:1px solid #fecaca;background:#7f1d1d;color:#fff1f2;'><div style='font-weight:900;'>❌ SOLD THIS SLIP</div><div style='margin-top:6px;'><strong>{sold_label}</strong> — {sold_market}<br>Target: {sold_target}<br>Final: {sold_final}<br>Missed by: {sold_miss}<br>Game: {sold_game}</div></div>"

    stake_text = f"${row.stake_amount:.2f}" if row.stake_amount is not None else '—'
    bet_date_text = row.bet_date.date().isoformat() if row.bet_date else '—'
    html = (
        "<!doctype html><html><head><title>ParlayBot Result</title>"
        "<style>body{font-family:Arial,Helvetica,sans-serif;margin:40px;max-width:1100px;color:#0f172a;line-height:1.45;}"
        ".card{border:1px solid #e2e8f0;border-radius:12px;padding:18px;background:#fff;}"
        ".meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px 16px;margin:10px 0 14px;}"
        ".tableWrap{overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;}"
        "table{width:100%;border-collapse:collapse;table-layout:fixed;}"
        "th,td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}"
        "th{font-size:12px;text-transform:uppercase;color:#64748b;}"
        "th:nth-child(1),td:nth-child(1){width:42%;}"
        "th:nth-child(2),td:nth-child(2){width:14%;}"
        "th:nth-child(3),td:nth-child(3){width:24%;}"
        "th:nth-child(4),td:nth-child(4){width:20%;}"
        "ul{padding-left:20px;margin-top:8px;}li{margin-bottom:6px;overflow-wrap:anywhere;}"
        "a{text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:700;display:inline-block;margin-top:16px;}"
        ".cta{background:#0f172a;color:#fff;}"
        "</style></head><body>"
        f"<h1>ParlayBot Result</h1><div class='card'><div><strong>Overall:</strong> {result_label}</div>"
        f"<div class='meta'><div><strong>Public ID:</strong> {escape(row.public_id)}</div><div><strong>Parser confidence:</strong> {escape(row.parser_confidence or 'low')}</div>"
        f"<div><strong>Bet date:</strong> {bet_date_text}</div><div><strong>Stake:</strong> {stake_text}</div><div><strong>Checked at:</strong> {escape(checked_at)}</div></div>"
        f"{sold_html}<h3>Leg Results ({len(legs)})</h3><div class='tableWrap'><table><thead><tr><th>Leg</th><th>Result</th><th>Matched Event</th><th>Review Reason</th></tr></thead><tbody>{''.join(leg_rows)}</tbody></table></div>"
        f"<h3>Matched Events</h3><ul>{events_html}</ul><div style='margin-top:12px;padding:10px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;'><strong>Share card:</strong> Open this slip in the main checker to download the PNG card.</div></div><div style='margin-top:16px;'><a class='cta' href='/check'>Check another slip</a></div></body></html>"
    )
    return HTMLResponse(html)


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
    return _grade_text_with_observability(req.text, posted_at=req.posted_at, bet_date=parsed_bet_date)


@app.post('/tickets/grade-and-save', response_model=TicketDetailResponse)
def grade_and_save_endpoint(req: GradeRequest, db: Session = Depends(get_db)) -> TicketDetailResponse:
    try:
        parsed_bet_date = date.fromisoformat(req.bet_date) if req.bet_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='bet_date must be YYYY-MM-DD') from exc
    result = _grade_text_with_observability(req.text, posted_at=req.posted_at, bet_date=parsed_bet_date)
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
    result = _grade_text_with_observability(normalized['cleaned_text'], posted_at=req.posted_at)
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
    result = _grade_text_with_observability(normalized['cleaned_text'], posted_at=req.posted_at)
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
    result = _grade_text_with_observability(normalized['cleaned_text'], posted_at=effective_posted_at)
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
    result = _grade_text_with_observability(normalized['cleaned_text'], posted_at=effective_posted_at)
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


@app.post('/ingest/screenshot/parse', response_model=ScreenshotParseResponse)
async def ingest_screenshot_parse(file: UploadFile = File(...)) -> ScreenshotParseResponse:
    content = await file.read()
    try:
        validate_image_upload(file.filename or 'upload', content)
        parsed_screenshot = _parse_screenshot_with_vision(content, file.filename or 'upload')
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cleaned_text = _screenshot_parsed_to_grading_text(parsed_screenshot)
    return ScreenshotParseResponse(
        source_ref=file.filename or 'upload',
        extracted_text=parsed_screenshot.raw_text,
        cleaned_text=cleaned_text,
        parsed_screenshot=parsed_screenshot,
    )


@app.post('/debug/vision/sanity', response_model=VisionSanityDebugResponse)
async def debug_vision_sanity(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
) -> VisionSanityDebugResponse:
    content = await file.read()
    requested_model = (model or '').strip() or None
    if requested_model and requested_model not in _VISION_SANITY_MODELS:
        raise HTTPException(status_code=400, detail=f'Unsupported model override. Allowed: {", ".join(sorted(_VISION_SANITY_MODELS))}')

    try:
        validate_image_upload(file.filename or 'upload', content)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sanity = OpenAIVisionSlipParser().run_sanity_check(content, model_override=requested_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VisionSanityDebugResponse(
        raw_response_text=sanity.raw_response_text,
        model_used=sanity.model_used,
        input_image_attached=sanity.input_image_attached,
        preprocessing_metadata=sanity.preprocessing_metadata,
    )


@app.get('/admin/debug/snapshots')
def admin_debug_snapshots_endpoint(_: str = Depends(require_admin)) -> dict[str, object]:
    if not debug_observability_enabled():
        raise HTTPException(status_code=404, detail='Debug observability endpoint disabled')
    return get_debug_observability_service().get_observability_snapshot()




@app.get('/admin/debug/hydration-candidates')
def admin_debug_hydration_candidates_endpoint(
    _: str = Depends(require_admin),
    max_event_ids: int = 20,
    max_dates: int = 10,
) -> dict[str, object]:
    if not debug_observability_enabled():
        raise HTTPException(status_code=404, detail='Debug observability endpoint disabled')
    return get_debug_observability_service().get_hydration_candidates_from_observability(
        max_event_ids=max_event_ids,
        max_dates=max_dates,
    )


@app.get('/admin/debug/market-readiness')
def admin_debug_market_readiness_endpoint(_: str = Depends(require_admin)) -> dict[str, object]:
    if not debug_observability_enabled():
        raise HTTPException(status_code=404, detail='Debug observability endpoint disabled')
    return get_debug_observability_service().get_snapshot_market_coverage_report()


@app.get('/admin/debug/period-readiness')
def admin_debug_period_readiness_endpoint(
    _: str = Depends(require_admin),
    max_snapshots: int = 250,
) -> dict[str, object]:
    if not debug_observability_enabled():
        raise HTTPException(status_code=404, detail='Debug observability endpoint disabled')
    return get_debug_observability_service().get_period_snapshot_availability_report(max_snapshots=max_snapshots)


@app.post('/admin/debug/hydrate-hotspots')
def admin_debug_hydrate_hotspots_endpoint(
    _: str = Depends(require_admin),
    max_event_ids: int = 20,
    max_dates: int = 10,
    default_sport: str = 'NBA',
) -> dict[str, object]:
    if not debug_observability_enabled():
        raise HTTPException(status_code=404, detail='Debug observability endpoint disabled')

    hydrator = SnapshotHydrator(observability_service=get_debug_observability_service())
    return hydrator.hydrate_observed_hotspots(
        default_sport=default_sport,
        max_event_ids=max_event_ids,
        max_dates=max_dates,
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
        parsed_screenshot = _parse_screenshot_with_vision(content, file.filename or 'upload')
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_posted_at = datetime.fromisoformat(posted_at) if posted_at else None
    grading_text = _screenshot_parsed_to_grading_text(parsed_screenshot)
    parsed_slip = parse_slip_text(grading_text, bookmaker_hint=bookmaker_hint)
    financials = extract_financials(parsed_screenshot.raw_text, bookmaker_hint=parsed_slip.bookmaker)
    parsed_bet_date = date.fromisoformat(bet_date) if bet_date else None
    screenshot_default_date = date.fromisoformat(parsed_screenshot.detected_bet_date) if parsed_screenshot.detected_bet_date else None
    grading_text = grading_text or parsed_slip.cleaned_text
    result = _grade_text_with_observability(grading_text, posted_at=parsed_posted_at, bet_date=parsed_bet_date, screenshot_default_date=screenshot_default_date, code_path='screenshot_parse_grading')
    return IngestGradeResponse(
        source_type='screenshot',
        source_ref=file.filename or 'upload',
        extracted_text=parsed_screenshot.raw_text,
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
        parsed_screenshot = _parse_screenshot_with_vision(content, file.filename or 'upload')
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_posted_at = datetime.fromisoformat(posted_at) if posted_at else None
    grading_text = _screenshot_parsed_to_grading_text(parsed_screenshot)
    parsed_slip = parse_slip_text(grading_text, bookmaker_hint=bookmaker_hint)
    financials = extract_financials(parsed_screenshot.raw_text, bookmaker_hint=parsed_slip.bookmaker)
    parsed_bet_date = date.fromisoformat(bet_date) if bet_date else None
    screenshot_default_date = date.fromisoformat(parsed_screenshot.detected_bet_date) if parsed_screenshot.detected_bet_date else None
    grading_text = grading_text or parsed_slip.cleaned_text
    result = _grade_text_with_observability(grading_text, posted_at=parsed_posted_at, bet_date=parsed_bet_date, screenshot_default_date=screenshot_default_date, code_path='saved_screenshot_grading')
    ticket = save_graded_ticket(
        db,
        grading_text,
        result,
        posted_at=parsed_posted_at,
        source_type='screenshot',
        source_ref=file.filename or 'upload',
        source_payload_json=dump_source_payload({
            'screenshot_parser': 'vision_primary_ocr_fallback',
            'raw_text': parsed_screenshot.raw_text,
            'bookmaker': parsed_slip.bookmaker,
            'bookmaker_notes': parsed_slip.notes,
            'financial_notes': financials.notes,
            'parsed_screenshot': parsed_screenshot.model_dump(),
            'settlement_explanations': [
                leg.settlement_explanation.model_dump() if leg.settlement_explanation else None
                for leg in result.legs
            ],
        }),
        bookmaker=financials.bookmaker,
        stake_amount=financials.stake_amount,
        to_win_amount=financials.to_win_amount,
        american_odds=financials.american_odds,
        decimal_odds=financials.decimal_odds,
    )
    enqueue_review_if_needed(db, ticket, result, ocr_confidence=0.5 if parsed_screenshot.confidence == 'low' else 0.9)
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
