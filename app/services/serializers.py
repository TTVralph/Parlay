from __future__ import annotations

import json

from ..db.models import AliasOverrideORM, PollRunORM, ReviewQueueORM, TicketORM, WatchedAccountORM
from ..models import AliasResponse, GradeResponse, GradedLeg, Leg, PollRunResponse, ReviewQueueItemResponse, TicketDetailResponse, WatchAccountResponse


def review_item_to_response(item: ReviewQueueORM) -> ReviewQueueItemResponse:
    return ReviewQueueItemResponse(
        review_id=item.id,
        ticket_id=item.ticket_id,
        status=item.status,
        priority=item.priority,
        reason_code=item.reason_code,
        summary=item.summary,
        resolution_note=item.resolution_note,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


def ticket_to_response(ticket: TicketORM) -> TicketDetailResponse:
    result = GradeResponse(
        overall=ticket.overall,
        legs=[
            GradedLeg(
                leg=Leg(
                    raw_text=leg.raw_text,
                    sport=leg.sport,
                    market_type=leg.market_type,  # type: ignore[arg-type]
                    team=leg.team,
                    player=leg.player,
                    direction=leg.direction,  # type: ignore[arg-type]
                    line=leg.line,
                    display_line=leg.display_line,
                    confidence=leg.confidence,
                    notes=json.loads(leg.notes_json),
                    event_id=leg.event_id,
                    event_label=leg.event_label,
                    event_start_time=leg.event_start_time,
                    matched_by=leg.matched_by,
                ),
                settlement=leg.settlement,  # type: ignore[arg-type]
                actual_value=leg.actual_value,
                reason=leg.reason,
            )
            for leg in ticket.legs
        ],
    )
    return TicketDetailResponse(
        ticket_id=ticket.id,
        raw_text=ticket.raw_text,
        overall=ticket.overall,
        created_at=ticket.created_at,
        posted_at=ticket.posted_at,
        source_type=ticket.source_type,
        source_ref=ticket.source_ref,
        bookmaker=ticket.bookmaker,
        stake_amount=ticket.stake_amount,
        to_win_amount=ticket.to_win_amount,
        american_odds=ticket.american_odds,
        decimal_odds=ticket.decimal_odds,
        profit_amount=ticket.profit_amount,
                is_duplicate=bool(ticket.duplicate_of_ticket_id),
        duplicate_of_ticket_id=ticket.duplicate_of_ticket_id,
        dedupe_key=ticket.dedupe_key,
        result=result,
        review_items=[review_item_to_response(item) for item in ticket.review_items],
    )


def watched_account_to_response(item: WatchedAccountORM) -> WatchAccountResponse:
    return WatchAccountResponse(
        id=item.id,
        username=item.username,
        poll_interval_minutes=item.poll_interval_minutes,
        is_enabled=item.is_enabled,
        last_polled_at=item.last_polled_at,
        last_seen_source_ref=item.last_seen_source_ref,
        created_at=item.created_at,
    )


def poll_run_to_response(item: PollRunORM) -> PollRunResponse:
    return PollRunResponse(
        run_id=item.id,
        watched_account_id=item.watched_account_id,
        username=item.username,
        status=item.status,
        fetched_count=item.fetched_count,
        saved_count=item.saved_count,
        detail=item.detail,
        created_at=item.created_at,
    )


def alias_to_response(item: AliasOverrideORM) -> AliasResponse:
    return AliasResponse(
        id=item.id,
        alias_type=item.alias_type,
        alias=item.alias,
        canonical_value=item.canonical_value,
        created_by=item.created_by,
        created_at=item.created_at,
    )
