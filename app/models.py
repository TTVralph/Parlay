from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Sport = Literal["NBA", "NFL", "MLB"]
MarketType = Literal[
    "moneyline",
    "spread",
    "game_total",
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_steals",
    "player_blocks",
    "player_turnovers",
    "player_pra",
    "player_pr",
    "player_pa",
    "player_ra",
    "player_passing_yards",
    "player_rushing_yards",
    "player_receiving_yards",
    "player_hits",
    "player_triple_double",
    "player_double_double",
    "player_first_basket",
    "player_first_rebound",
    "player_first_assist",
    "player_first_three",
    "player_last_basket",
    "player_first_steal",
    "player_first_block",
]
Direction = Literal["over", "under", "yes", "no"]
Settlement = Literal["win", "loss", "pending", "push", "void", "unmatched"]
ReviewStatus = Literal["open", "approved", "rejected"]
ReviewPriority = Literal["low", "normal", "high"]


class ParseRequest(BaseModel):
    text: str = Field(..., description="Raw parlay text pasted by user")
    sport_hint: Optional[Sport] = None


class Leg(BaseModel):
    leg_id: Optional[str] = None
    raw_text: str
    sport: Sport = "NBA"
    market_type: MarketType
    team: Optional[str] = None
    player: Optional[str] = None
    direction: Optional[Direction] = None
    line: Optional[float] = None
    display_line: Optional[str] = None
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)
    event_id: Optional[str] = None
    event_label: Optional[str] = None
    event_start_time: Optional[datetime] = None
    matched_by: Optional[str] = None
    event_candidates: list[dict[str, Any]] = Field(default_factory=list)
    resolved_player_name: Optional[str] = None
    resolved_team: Optional[str] = None
    selected_bet_date: Optional[str] = None
    parsed_player_name: Optional[str] = None
    normalized_stat_type: Optional[str] = None
    resolved_player_id: Optional[str] = None
    resolution_confidence: Optional[float] = None
    resolution_ambiguity_reason: Optional[str] = None
    candidate_players: list[str] = Field(default_factory=list)
    candidate_player_details: list[dict[str, Any]] = Field(default_factory=list)
    parse_confidence: Optional[float] = None
    identity_source: Optional[str] = None
    identity_last_refreshed_at: Optional[str] = None
    identity_match_method: Optional[str] = None
    identity_match_confidence: Optional[Literal['HIGH', 'MEDIUM', 'LOW']] = None
    resolved_team_hint: Optional[str] = None
    matched_event_id: Optional[str] = None
    matched_event_label: Optional[str] = None
    matched_event_date: Optional[str] = None
    matched_team: Optional[str] = None
    event_resolution_confidence: Optional[Literal['high', 'medium', 'low']] = None
    event_resolution_warnings: list[str] = Field(default_factory=list)
    slip_default_date: Optional[str] = None
    mixed_event_dates_detected: Optional[bool] = None
    event_resolution_status: Optional[str] = None
    event_resolution_method: Optional[str] = None
    event_review_reason_code: Optional[str] = None
    event_review_reason_text: Optional[str] = None
    event_date_match_quality: Optional[Literal['exact', 'nearby', 'mismatch', 'unknown']] = None
    roster_validation_result: Optional[Literal['pass', 'fail', 'unknown']] = None
    american_odds: Optional[int] = None
    decimal_odds: Optional[float] = None
    selected_player_name: Optional[str] = None
    selected_player_id: Optional[str] = None
    selection_source: Optional[Literal['auto', 'user_selected']] = None
    selection_explanation: Optional[str] = None
    selection_applied: bool = False
    selection_error_code: Optional[str] = None
    canonical_player_name: Optional[str] = None
    event_selection_applied: bool = False
    selected_event_id: Optional[str] = None
    selected_event_label: Optional[str] = None
    event_selection_source: Optional[Literal['auto', 'user_selected']] = None
    event_selection_explanation: Optional[str] = None
    override_used_for_grading: bool = False


class ParseResponse(BaseModel):
    legs: list[Leg]


class GradeRequest(BaseModel):
    text: str
    sport_hint: Optional[Sport] = None
    posted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp for the original post/slip, used for event/date resolution",
    )
    bet_date: Optional[str] = Field(default=None, description='Optional bet/slip date in YYYY-MM-DD format')


class GradedLeg(BaseModel):
    leg: Leg
    settlement: Settlement
    actual_value: Optional[float] = None
    reason: str
    matched_event: Optional[str] = None
    line: Optional[float] = None
    normalized_market: Optional[str] = None
    component_values: Optional[dict[str, float]] = None
    explanation_reason: Optional[str] = None
    candidate_games: list[dict[str, Any]] = Field(default_factory=list)
    candidate_events: list[dict[str, Any]] = Field(default_factory=list)
    player_found_in_boxscore: Optional[bool] = None
    review_reason: Optional[str] = None
    resolved_player_name: Optional[str] = None
    resolved_team: Optional[str] = None
    selected_bet_date: Optional[str] = None
    parsed_player_name: Optional[str] = None
    normalized_stat_type: Optional[str] = None
    resolved_player_id: Optional[str] = None
    matched_boxscore_player_name: Optional[str] = None
    resolution_confidence: Optional[float] = None
    resolution_ambiguity_reason: Optional[str] = None
    candidate_players: list[str] = Field(default_factory=list)
    candidate_player_details: list[dict[str, Any]] = Field(default_factory=list)
    parse_confidence: Optional[float] = None
    identity_source: Optional[str] = None
    identity_last_refreshed_at: Optional[str] = None
    identity_match_method: Optional[str] = None
    identity_match_confidence: Optional[Literal['HIGH', 'MEDIUM', 'LOW']] = None
    resolved_team_hint: Optional[str] = None
    validation_warnings: list[str] = Field(default_factory=list)
    settlement_explanation: Optional['SettlementExplanation'] = None
    settlement_diagnostics: dict[str, Any] = Field(default_factory=dict)
    matched_event_date: Optional[str] = None
    matched_team: Optional[str] = None
    event_resolution_confidence: Optional[Literal['high', 'medium', 'low']] = None
    event_resolution_warnings: list[str] = Field(default_factory=list)
    slip_default_date: Optional[str] = None
    mixed_event_dates_detected: Optional[bool] = None
    event_resolution_status: Optional[str] = None
    event_resolution_method: Optional[str] = None
    event_review_reason_code: Optional[str] = None
    event_review_reason_text: Optional[str] = None
    event_date_match_quality: Optional[Literal['exact', 'nearby', 'mismatch', 'unknown']] = None
    roster_validation_result: Optional[Literal['pass', 'fail', 'unknown']] = None
    input_source_path: Optional[Literal['manual_text', 'screenshot']] = None
    debug_comparison: dict[str, Any] = Field(default_factory=dict)
    review_reason_text: Optional[str] = None
    selected_player_name: Optional[str] = None
    selected_player_id: Optional[str] = None
    selection_source: Optional[Literal['auto', 'user_selected']] = None
    selection_explanation: Optional[str] = None
    selection_applied: bool = False
    selection_error_code: Optional[str] = None
    canonical_player_name: Optional[str] = None
    event_selection_applied: bool = False
    selected_event_id: Optional[str] = None
    selected_event_label: Optional[str] = None
    event_selection_source: Optional[Literal['auto', 'user_selected']] = None
    event_selection_explanation: Optional[str] = None
    override_used_for_grading: bool = False


class SettlementExplanation(BaseModel):
    raw_leg_text: str
    raw_player_text: Optional[str] = None
    matched_canonical_player: Optional[str] = None
    matched_team: Optional[str] = None
    identity_match_method: Optional[str] = None
    identity_confidence: Optional[float] = None
    matched_event: Optional[str] = None
    matched_market: Optional[str] = None
    normalized_selection: Optional[str] = None
    line: Optional[float] = None
    actual_stat_value: Optional[float] = None
    stat_components: list[str] = Field(default_factory=list)
    component_values: dict[str, float] = Field(default_factory=dict)
    computed_total: Optional[float] = None
    result: Settlement = 'unmatched'
    settlement_reason_code: str
    settlement_reason: str
    warnings: list[str] = Field(default_factory=list)
    grading_confidence: float = 0.0
    matched_player: Optional[str] = None
    normalized_market: Optional[str] = None
    stat_field_used: Optional[str] = None
    selection: Optional[str] = None
    settlement_reason_text: Optional[str] = None


class GradeResponse(BaseModel):
    overall: Literal["cashed", "lost", "pending", "needs_review"]
    legs: list[GradedLeg]
    grading_diagnostics: dict[str, Any] = Field(default_factory=dict)


class AllSportsGame(BaseModel):
    id: str
    homeTeam: str | None = None
    awayTeam: str | None = None
    status: str | None = None
    startTime: Any = None


class AllSportsGamesResponse(BaseModel):
    date: str
    games: list[AllSportsGame] = Field(default_factory=list)


class AllSportsStatsResponse(BaseModel):
    matchId: str
    homeTeam: str | None = None
    awayTeam: str | None = None
    teamStats: list[dict[str, Any]] = Field(default_factory=list)
    playerStats: list[dict[str, Any]] | None = None


class SportsAPIProGame(BaseModel):
    id: str
    competitionId: str | None = None
    competitionName: str | None = None
    homeTeam: str | None = None
    awayTeam: str | None = None
    homeTeamId: str | None = None
    awayTeamId: str | None = None
    status: str | None = None
    startTime: str | None = None


class SportsAPIProGamesResponse(BaseModel):
    games: list[SportsAPIProGame] = Field(default_factory=list)


class SportsAPIProPlayerStats(BaseModel):
    minutes: int = 0
    points: int = 0
    rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    fieldGoalsMade: int = 0
    fieldGoalsAttempted: int = 0
    threePointersMade: int = 0
    threePointersAttempted: int = 0
    freeThrowsMade: int = 0
    freeThrowsAttempted: int = 0
    offensiveRebounds: int = 0
    defensiveRebounds: int = 0
    turnovers: int = 0
    personalFouls: int = 0
    plusMinus: int = 0


class SportsAPIProAthleteGameLog(BaseModel):
    athleteId: str
    gameId: str | None = None
    date: str | None = None
    opponentId: str | None = None
    opponentName: str | None = None
    competitionId: str | None = None
    competitionName: str | None = None
    stats: SportsAPIProPlayerStats = Field(default_factory=SportsAPIProPlayerStats)


class SportsAPIProAthleteGameLogsResponse(BaseModel):
    athleteId: str
    logs: list[SportsAPIProAthleteGameLog] = Field(default_factory=list)


class SportsAPIProAthleteGamesResponse(BaseModel):
    athleteId: str
    logs: list[SportsAPIProAthleteGameLog] = Field(default_factory=list)


class ProviderCapabilities(BaseModel):
    supports_game_results: bool
    supports_team_stats: bool
    supports_player_props: bool
    supports_live_status: bool


class ProviderCapabilitiesResponse(BaseModel):
    providers: dict[str, ProviderCapabilities]


class CheckJobCreateResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: Literal["pending"] = "pending"


class CheckJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "complete", "failed"]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class TweetIngestRequest(BaseModel):
    tweet_id: Optional[str] = None
    username: Optional[str] = None
    text: str
    quoted_text: Optional[str] = None
    note_text: Optional[str] = None
    media_text: list[str] = Field(default_factory=list)
    posted_at: Optional[datetime] = None


class XFetchRequest(BaseModel):
    tweet_id: str
    posted_at: Optional[datetime] = None




class ParsedScreenshotLeg(BaseModel):
    raw_leg_text: str
    raw_player_text: Optional[str] = None
    player_name: Optional[str] = None
    stat_type: Optional[str] = None
    line: Optional[float] = None
    direction: Optional[Direction] = None
    normalized_label: str
    confidence: Optional[float] = None
    match_method: Optional[str] = None
    match_confidence: Optional[Literal['HIGH', 'MEDIUM', 'LOW']] = None
    suggested_player_name: Optional[str] = None
    suggestion_confidence: Optional[float] = None
    suggestion_confidence_level: Optional[Literal['HIGH', 'MEDIUM']] = None
    suggestion_auto_applied: bool = False


class ScreenshotPreprocessingMetadata(BaseModel):
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    crop_applied: bool
    crop_box: Optional[list[int]] = None
    resize_applied: bool
    compressed: bool


class PrimaryParserDebug(BaseModel):
    primary_parser_status: str = 'not_attempted'
    primary_failure_category: Optional[str] = None
    primary_provider_error: Optional[str] = None
    primary_confidence: Optional[str] = None
    primary_warnings: list[str] = Field(default_factory=list)
    primary_detected_sportsbook: Optional[str] = None
    primary_parser_strategy_used: Optional[str] = None
    primary_screenshot_state: Optional[str] = None
    primary_parsed_leg_count: int = 0


class ParsedScreenshotResponse(BaseModel):
    raw_text: str
    parsed_legs: list[ParsedScreenshotLeg] = Field(default_factory=list)
    detected_bet_date: Optional[str] = None
    parse_warnings: list[str] = Field(default_factory=list)
    confidence: Literal['high', 'medium', 'low', 'NEEDS_REVIEW'] = 'low'
    preprocessing_metadata: Optional[ScreenshotPreprocessingMetadata] = None
    primary_parser_debug: Optional[PrimaryParserDebug] = None
    primary_pre_fallback_result: Optional['ParsedScreenshotResponse'] = None
    fallback_reason: Optional[str] = None
    debug_artifacts: Optional[dict[str, str]] = None

class OCRExtractResponse(BaseModel):
    filename: str
    raw_text: str
    cleaned_text: str
    provider: str
    confidence: float
    notes: list[str] = Field(default_factory=list)


class ScreenshotParseResponse(BaseModel):
    source_ref: str
    extracted_text: str
    cleaned_text: str
    parsed_screenshot: ParsedScreenshotResponse


class VisionSanityDebugResponse(BaseModel):
    raw_response_text: str
    model_used: str
    input_image_attached: bool
    preprocessing_metadata: ScreenshotPreprocessingMetadata


class IngestGradeResponse(BaseModel):
    source_type: Literal["tweet", "screenshot"]
    source_ref: Optional[str] = None
    extracted_text: str
    cleaned_text: str
    posted_at: Optional[datetime] = None
    bookmaker: Optional[str] = None
    stake_amount: Optional[float] = None
    to_win_amount: Optional[float] = None
    american_odds: Optional[int] = None
    decimal_odds: Optional[float] = None
    parsed_screenshot: Optional[ParsedScreenshotResponse] = None
    result: GradeResponse


class ReviewQueueItemResponse(BaseModel):
    review_id: int
    ticket_id: str
    status: ReviewStatus
    priority: ReviewPriority
    reason_code: str
    summary: str
    resolution_note: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ReviewResolveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    resolution_note: str


class TicketFinancialsUpdateRequest(BaseModel):
    stake_amount: Optional[float] = None
    to_win_amount: Optional[float] = None
    american_odds: Optional[int] = None
    decimal_odds: Optional[float] = None
    bookmaker: Optional[str] = None


class LegManualEdit(BaseModel):
    leg_index: int
    team: Optional[str] = None
    player: Optional[str] = None
    market_type: Optional[MarketType] = None
    direction: Optional[Direction] = None
    line: Optional[float] = None
    display_line: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[list[str]] = None
    event_id: Optional[str] = None
    event_label: Optional[str] = None
    matched_by: Optional[str] = None


class ManualTicketRegradeRequest(BaseModel):
    legs: list[LegManualEdit] = Field(default_factory=list)
    posted_at: Optional[datetime] = None
    financials: Optional[TicketFinancialsUpdateRequest] = None
    resolve_review_id: Optional[int] = None
    resolution_note: Optional[str] = None


class SlipTemplateResponse(BaseModel):
    bookmaker: str
    title: str
    template_text: str
    notes: list[str] = Field(default_factory=list)


class CapperRoiDashboardRow(BaseModel):
    username: str
    settled_with_stake: int
    wins_with_stake: int
    losses_with_stake: int
    total_staked: float
    total_profit: float
    roi: float
    avg_stake: float


class CapperRoiDashboardResponse(BaseModel):
    rows: list[CapperRoiDashboardRow] = Field(default_factory=list)


class TicketDetailResponse(BaseModel):
    ticket_id: str
    raw_text: str
    overall: Literal["cashed", "lost", "pending", "needs_review"]
    created_at: datetime
    posted_at: Optional[datetime] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    bookmaker: Optional[str] = None
    stake_amount: Optional[float] = None
    to_win_amount: Optional[float] = None
    american_odds: Optional[int] = None
    decimal_odds: Optional[float] = None
    profit_amount: Optional[float] = None
    is_duplicate: bool = False
    duplicate_of_ticket_id: Optional[str] = None
    dedupe_key: Optional[str] = None
    result: GradeResponse
    review_items: list[ReviewQueueItemResponse] = Field(default_factory=list)


class WatchAccountRequest(BaseModel):
    username: str
    poll_interval_minutes: int = 15
    is_enabled: bool = True


class WatchAccountResponse(BaseModel):
    id: int
    username: str
    poll_interval_minutes: int
    is_enabled: bool
    last_polled_at: Optional[datetime] = None
    last_seen_source_ref: Optional[str] = None
    created_at: datetime


class PollAccountRequest(BaseModel):
    max_tweets: int = 5


class PollRunResponse(BaseModel):
    run_id: int
    watched_account_id: Optional[int] = None
    username: str
    status: str
    fetched_count: int
    saved_count: int
    detail: Optional[str] = None
    created_at: datetime


class AliasUpsertRequest(BaseModel):
    alias_type: Literal["player", "team", "market"]
    alias: str
    canonical_value: str
    created_by: Optional[str] = None


class AliasResponse(BaseModel):
    id: int
    alias_type: str
    alias: str
    canonical_value: str
    created_by: Optional[str] = None
    created_at: datetime


class SlipParseRequest(BaseModel):
    text: str
    bookmaker_hint: Optional[str] = None


class SlipParseResponse(BaseModel):
    bookmaker: str
    cleaned_text: str
    notes: list[str] = Field(default_factory=list)
    stake_amount: Optional[float] = None
    to_win_amount: Optional[float] = None
    american_odds: Optional[int] = None
    decimal_odds: Optional[float] = None


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    interval_seconds: int


class SchedulerRunResponse(BaseModel):
    triggered_accounts: int
    created_runs: int


class TicketDeduplicationResponse(BaseModel):
    is_duplicate: bool
    duplicate_of_ticket_id: Optional[str] = None
    dedupe_key: str


class CapperDashboardRow(BaseModel):
    username: str
    total_tickets: int
    unique_tickets: int
    duplicate_tickets: int
    cashed: int
    lost: int
    pending: int
    needs_review: int
    settled_tickets: int
    hit_rate: float


class CapperDashboardResponse(BaseModel):
    rows: list[CapperDashboardRow] = Field(default_factory=list)


class OddsMatchLegResponse(BaseModel):
    raw_text: str
    bookmaker: str
    matched: bool
    event_id: Optional[str] = None
    market_type: Optional[MarketType] = None
    selection: Optional[str] = None
    line: Optional[float] = None
    offered_american_odds: Optional[int] = None
    reason: str


class OddsMatchRequest(BaseModel):
    text: str
    bookmaker: str
    posted_at: Optional[datetime] = None


class OddsMatchResponse(BaseModel):
    bookmaker: str
    matched_legs: list[OddsMatchLegResponse] = Field(default_factory=list)
    matched_count: int
    total_count: int


class PublicCapperProfileResponse(BaseModel):
    username: str
    verified: bool = False
    verification_badge: Optional[str] = None
    summary: CapperDashboardRow
    roi_summary: Optional[CapperRoiDashboardRow] = None
    recent_tickets: list[TicketDetailResponse] = Field(default_factory=list)


class AdminAuthStatusResponse(BaseModel):
    authenticated: bool


class ModerationRequest(BaseModel):
    reason: Optional[str] = None


class CapperModerationResponse(BaseModel):
    username: str
    is_public: bool
    moderation_note: Optional[str] = None


class PublicLeaderboardRow(BaseModel):
    username: str
    hit_rate: float
    roi: Optional[float] = None
    settled_tickets: int


class PublicLeaderboardResponse(BaseModel):
    rows: list[PublicLeaderboardRow] = Field(default_factory=list)


class UserRegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: Literal["member", "capper"] = "member"
    linked_capper_username: Optional[str] = None


class UserLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool = False
    role: str = "member"
    linked_capper_username: Optional[str] = None
    created_at: datetime


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: Optional[datetime] = None
    user: UserProfileResponse


class LogoutResponse(BaseModel):
    success: bool


class AdminSessionRow(BaseModel):
    session_id: int
    username: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    is_active: bool


class AdminSessionsResponse(BaseModel):
    rows: list[AdminSessionRow] = Field(default_factory=list)


class UserRoleUpdateRequest(BaseModel):
    role: Literal["member", "capper", "admin"]
    linked_capper_username: Optional[str] = None


class AdminCapperCreateRequest(BaseModel):
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    is_public: bool = True
    moderation_note: Optional[str] = None


class AdminCapperUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    is_public: Optional[bool] = None
    moderation_note: Optional[str] = None


class AdminCapperProfileResponse(BaseModel):
    username: str
    is_public: bool
    moderation_note: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    verified: bool = False
    verification_badge: Optional[str] = None


class CapperSelfProfileResponse(BaseModel):
    username: str
    is_public: bool
    moderation_note: Optional[str] = None
    claimed_by_user_id: Optional[int] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    verified: bool = False
    verification_badge: Optional[str] = None


class CapperSelfProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    is_public: Optional[bool] = None


class SubscriptionPlanResponse(BaseModel):
    code: str
    name: str
    price_monthly: float
    features: list[str] = Field(default_factory=list)
    is_active: bool = True


class SubscriptionPlansResponse(BaseModel):
    rows: list[SubscriptionPlanResponse] = Field(default_factory=list)


class SubscriptionCheckoutRequest(BaseModel):
    plan_code: str
    provider: str = "mock_stripe"


class SubscriptionCheckoutResponse(BaseModel):
    subscription_id: int
    plan_code: str
    status: str
    provider: str
    checkout_url: str


class UserSubscriptionResponse(BaseModel):
    subscription_id: int
    plan_code: str
    status: str
    provider: str
    provider_customer_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    started_at: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False


class AffiliateLinkUpsertRequest(BaseModel):
    bookmaker: str
    base_url: str
    affiliate_code: Optional[str] = None
    campaign_code: Optional[str] = None
    is_active: bool = True


class AffiliateLinkResponse(BaseModel):
    bookmaker: str
    base_url: str
    affiliate_code: Optional[str] = None
    campaign_code: Optional[str] = None
    is_active: bool = True


class AffiliateResolveRequest(BaseModel):
    bookmaker: str
    capper_username: Optional[str] = None
    ticket_id: Optional[str] = None
    source: str = "parlaybot"


class AffiliateResolveResponse(BaseModel):
    bookmaker: str
    resolved_url: str
    campaign_code: Optional[str] = None
    click_token: Optional[str] = None


class CapperVerificationRequest(BaseModel):
    badge: str = "verified"
    note: Optional[str] = None


class CapperVerificationResponse(BaseModel):
    username: str
    verified: bool
    verification_badge: Optional[str] = None
    verification_note: Optional[str] = None


class BillingEntitlementsResponse(BaseModel):
    plan_code: str = "free"
    is_active: bool = False
    entitlements: list[str] = Field(default_factory=list)


class StripeCheckoutRequest(BaseModel):
    plan_code: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class StripeWebhookEventRequest(BaseModel):
    id: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class StripeWebhookResponse(BaseModel):
    ok: bool = True
    processed: bool = True
    event_id: str
    event_type: str


class AffiliateAnalyticsRow(BaseModel):
    bookmaker: str
    clicks: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0
    revenue: float = 0.0
    unique_cappers: int = 0
    latest_click_at: Optional[datetime] = None


class AffiliateAnalyticsResponse(BaseModel):
    rows: list[AffiliateAnalyticsRow] = Field(default_factory=list)


class SubscriptionCancelRequest(BaseModel):
    immediate: bool = False


class BillingPortalRequest(BaseModel):
    return_url: Optional[str] = None


class BillingPortalResponse(BaseModel):
    url: str


class BillingEventRow(BaseModel):
    event_id: str
    event_type: str
    processed_at: datetime


class BillingAccountResponse(BaseModel):
    user: UserProfileResponse
    entitlements: BillingEntitlementsResponse
    subscription: Optional[UserSubscriptionResponse] = None
    plans: list[SubscriptionPlanResponse] = Field(default_factory=list)
    recent_billing_events: list[BillingEventRow] = Field(default_factory=list)


class BillingInvoiceRow(BaseModel):
    invoice_id: str
    provider_invoice_id: Optional[str] = None
    subscription_id: Optional[int] = None
    status: str
    amount_paid: float = 0.0
    currency: str = "usd"
    hosted_invoice_url: Optional[str] = None
    pdf_download_token: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    created_at: datetime


class BillingInvoicesResponse(BaseModel):
    rows: list[BillingInvoiceRow] = Field(default_factory=list)


class BillingHistoryResponse(BaseModel):
    invoices: list[BillingInvoiceRow] = Field(default_factory=list)
    recent_billing_events: list[BillingEventRow] = Field(default_factory=list)
    email_notifications: list["EmailNotificationRow"] = Field(default_factory=list)


class EmailNotificationRow(BaseModel):
    notification_id: int
    to_email: str
    template_key: str
    event_type: str
    subject: str
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class EmailNotificationsResponse(BaseModel):
    rows: list[EmailNotificationRow] = Field(default_factory=list)


class AffiliateConversionRecordRequest(BaseModel):
    click_token: str
    bookmaker: Optional[str] = None
    revenue_amount: Optional[float] = None
    currency: str = "usd"
    external_ref: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AffiliateConversionRow(BaseModel):
    conversion_id: int
    click_token: str
    bookmaker: str
    revenue_amount: float = 0.0
    currency: str = "usd"
    external_ref: Optional[str] = None
    created_at: datetime


class AffiliateConversionsResponse(BaseModel):
    rows: list[AffiliateConversionRow] = Field(default_factory=list)


class BillingInvoiceLinksResponse(BaseModel):
    invoice_id: str
    hosted_invoice_url: Optional[str] = None
    pdf_download_url: Optional[str] = None
    signed_public_pdf_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    pdf_filename: Optional[str] = None


class AffiliatePostbackRequest(BaseModel):
    click_token: Optional[str] = None
    bookmaker: Optional[str] = None
    revenue_amount: Optional[float] = None
    currency: str = "usd"
    external_ref: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AffiliateWebhookIngestRequest(BaseModel):
    click_token: Optional[str] = None
    bookmaker: Optional[str] = None
    revenue_amount: Optional[float] = None
    currency: str = "usd"
    external_ref: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AffiliateWebhookEventRow(BaseModel):
    event_id: int
    source_type: str
    network: Optional[str] = None
    external_ref: Optional[str] = None
    click_token: Optional[str] = None
    status: str
    conversion_id: Optional[int] = None
    payload_summary: Optional[str] = None
    created_at: datetime


class AffiliateWebhookEventsResponse(BaseModel):
    rows: list[AffiliateWebhookEventRow] = Field(default_factory=list)


class SignedInvoiceLinkResponse(BaseModel):
    invoice_id: str
    public_url: str
    expires_at: datetime
