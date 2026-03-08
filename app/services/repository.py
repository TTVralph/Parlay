from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from urllib.parse import urlencode
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..stripe_gateway import create_checkout_session, create_billing_portal
from ..emailer import send_email_message
from ..invoice_pdf import render_invoice_pdf_bytes
from ..db.models import (
    AliasOverrideORM,
    CapperProfileORM,
    AuditLogORM,
    PollRunORM,
    ReviewQueueORM,
    TicketLegORM,
    TicketORM,
    WatchedAccountORM,
    UserORM,
    UserSessionORM,
    SubscriptionPlanORM,
    UserSubscriptionORM,
    AffiliateLinkORM,
    AffiliateClickORM,
    AffiliateConversionORM,
    AffiliateWebhookEventORM,
    StripeEventORM,
    BillingInvoiceORM,
    EmailNotificationORM,
)
from ..models import GradeResponse, GradedLeg, Leg


def build_dedupe_key(raw_text: str, posted_at: datetime | None = None, source_type: str | None = None, source_ref: str | None = None) -> str:
    normalized = "\n".join(line.strip().lower() for line in raw_text.splitlines() if line.strip())
    day_key = posted_at.date().isoformat() if posted_at else 'na'
    base = f"{source_type or 'unknown'}|{source_ref or ''}|{day_key}|{normalized}"
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def find_duplicate_ticket(db: Session, raw_text: str, posted_at: datetime | None = None, source_type: str | None = None, source_ref: str | None = None) -> TicketORM | None:
    dedupe_key = build_dedupe_key(raw_text, posted_at=posted_at, source_type=source_type, source_ref=source_ref)
    return db.scalar(select(TicketORM).where(TicketORM.dedupe_key == dedupe_key).order_by(TicketORM.created_at.asc(), TicketORM.id.asc()))


def get_due_watched_accounts(db: Session, now: datetime | None = None) -> list[WatchedAccountORM]:
    now = now or datetime.utcnow()
    rows = list(db.scalars(select(WatchedAccountORM).where(WatchedAccountORM.is_enabled == True)).all())
    due: list[WatchedAccountORM] = []
    for row in rows:
        if row.last_polled_at is None:
            due.append(row)
            continue
        if row.last_polled_at <= now - timedelta(minutes=row.poll_interval_minutes):
            due.append(row)
    return due


def compute_capper_dashboard(db: Session, username: str | None = None, include_hidden: bool = False, public_only: bool = False) -> list[dict]:
    stmt = select(TicketORM).where(TicketORM.source_type == 'tweet')
    if not include_hidden:
        stmt = stmt.where(TicketORM.is_hidden == False)
    if username:
        username_key = username.lower().lstrip('@').strip()
        stmt = stmt.where(func.lower(TicketORM.source_ref).like(f'%/{username_key}/status/%'))
    tickets = list(db.scalars(stmt).all())
    buckets: dict[str, dict] = {}
    for ticket in tickets:
        source_ref = ticket.source_ref or ''
        capper = 'unknown'
        if '/status/' in source_ref:
            parts = source_ref.rstrip('/').split('/')
            try:
                idx = parts.index('x.com')
                capper = parts[idx + 1]
            except Exception:
                capper = parts[-3] if len(parts) >= 3 else source_ref
        elif ':' in source_ref:
            capper = source_ref.split(':', 1)[0]
        elif source_ref:
            capper = source_ref
        row = buckets.setdefault(capper, {'username': capper, 'total_tickets': 0, 'unique_tickets': 0, 'duplicate_tickets': 0, 'cashed': 0, 'lost': 0, 'pending': 0, 'needs_review': 0})
        row['total_tickets'] += 1
        if ticket.duplicate_of_ticket_id:
            row['duplicate_tickets'] += 1
        else:
            row['unique_tickets'] += 1
            row[ticket.overall] += 1
    results = []
    for row in buckets.values():
        settled = row['cashed'] + row['lost']
        row['settled_tickets'] = settled
        row['hit_rate'] = round((row['cashed'] / settled) if settled else 0.0, 4)
        results.append(row)
    if public_only:
        profiles = {row.username: row for row in db.scalars(select(CapperProfileORM)).all()}
        results = [row for row in results if profiles.get(row['username']) is None or profiles[row['username']].is_public]
    results.sort(key=lambda item: (-item['hit_rate'], -item['settled_tickets'], item['username']))
    return results


def american_odds_profit(stake_amount: float, american_odds: int) -> float:
    if american_odds > 0:
        return round(stake_amount * (american_odds / 100.0), 2)
    return round(stake_amount * (100.0 / abs(american_odds)), 2)


def settle_ticket_profit(overall: str, stake_amount: float | None = None, to_win_amount: float | None = None, american_odds: int | None = None) -> float | None:
    if stake_amount is None:
        return None
    if overall == 'cashed':
        if to_win_amount is not None:
            return round(to_win_amount, 2)
        if american_odds is not None and american_odds != 0:
            return american_odds_profit(stake_amount, american_odds)
        return None
    if overall == 'lost':
        return round(-stake_amount, 2)
    return None


def build_grade_from_legs(graded_legs: list[GradedLeg]) -> GradeResponse:
    settlements = [item.settlement for item in graded_legs]
    if any(settlement == 'loss' for settlement in settlements):
        overall = 'lost'
    elif settlements and all(settlement == 'win' for settlement in settlements):
        overall = 'cashed'
    elif any(settlement == 'pending' for settlement in settlements) and not any(settlement == 'unmatched' for settlement in settlements):
        overall = 'pending'
    else:
        overall = 'needs_review'
    return GradeResponse(overall=overall, legs=graded_legs)


def update_ticket_financials(db: Session, ticket: TicketORM, stake_amount: float | None = None, to_win_amount: float | None = None, american_odds: int | None = None, decimal_odds: float | None = None, bookmaker: str | None = None) -> TicketORM:
    ticket.stake_amount = stake_amount
    ticket.to_win_amount = to_win_amount
    ticket.american_odds = american_odds
    ticket.decimal_odds = decimal_odds
    ticket.bookmaker = bookmaker
    ticket.profit_amount = settle_ticket_profit(ticket.overall, stake_amount=stake_amount, to_win_amount=to_win_amount, american_odds=american_odds)
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='ticket_financials_updated', detail=f'stake={stake_amount} to_win={to_win_amount} american_odds={american_odds} decimal_odds={decimal_odds} bookmaker={bookmaker}'))
    db.commit()
    db.refresh(ticket)
    return ticket


def manual_regrade_ticket(db: Session, ticket: TicketORM, graded_legs: list[GradedLeg], posted_at: datetime | None = None, resolution_note: str | None = None) -> TicketORM:
    result = build_grade_from_legs(graded_legs)
    ticket.overall = result.overall
    if posted_at is not None:
        ticket.posted_at = posted_at
    ticket.sport = result.legs[0].leg.sport if result.legs else ticket.sport
    ticket.profit_amount = settle_ticket_profit(ticket.overall, stake_amount=ticket.stake_amount, to_win_amount=ticket.to_win_amount, american_odds=ticket.american_odds)
    for old_leg in list(ticket.legs):
        db.delete(old_leg)
    db.flush()
    for item in result.legs:
        leg = item.leg
        db.add(TicketLegORM(ticket_id=ticket.id, raw_text=leg.raw_text, sport=leg.sport, market_type=leg.market_type, team=leg.team, player=leg.player, direction=leg.direction, line=leg.line, display_line=leg.display_line, confidence=leg.confidence, notes_json=json.dumps(leg.notes), event_id=leg.event_id, event_label=leg.event_label, event_start_time=leg.event_start_time, matched_by=leg.matched_by, settlement=item.settlement, actual_value=item.actual_value, reason=item.reason))
    detail = f'manual regrade -> overall={ticket.overall}'
    if resolution_note:
        detail += f' | note={resolution_note}'
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='ticket_manual_regraded', detail=detail))
    db.commit()
    db.refresh(ticket)
    return ticket


def save_graded_ticket(db: Session, raw_text: str, result: GradeResponse, posted_at: datetime | None = None, source_type: str | None = None, source_ref: str | None = None, source_payload_json: str | None = None, bookmaker: str | None = None, stake_amount: float | None = None, to_win_amount: float | None = None, american_odds: int | None = None, decimal_odds: float | None = None) -> TicketORM:
    dedupe_key = build_dedupe_key(raw_text, posted_at=posted_at, source_type=source_type, source_ref=source_ref)
    duplicate = db.scalar(select(TicketORM).where(TicketORM.dedupe_key == dedupe_key).order_by(TicketORM.created_at.asc(), TicketORM.id.asc()))
    inferred_sport = result.legs[0].leg.sport if result.legs else 'NBA'
    ticket = TicketORM(raw_text=raw_text, overall=result.overall, sport=inferred_sport, posted_at=posted_at, source_type=source_type, source_ref=source_ref, source_payload_json=source_payload_json, bookmaker=bookmaker, stake_amount=stake_amount, to_win_amount=to_win_amount, american_odds=american_odds, decimal_odds=decimal_odds, profit_amount=settle_ticket_profit(result.overall, stake_amount=stake_amount, to_win_amount=to_win_amount, american_odds=american_odds), dedupe_key=dedupe_key, duplicate_of_ticket_id=duplicate.id if duplicate else None)
    db.add(ticket)
    db.flush()
    for item in result.legs:
        leg: Leg = item.leg
        db.add(TicketLegORM(ticket_id=ticket.id, raw_text=leg.raw_text, sport=leg.sport, market_type=leg.market_type, team=leg.team, player=leg.player, direction=leg.direction, line=leg.line, display_line=leg.display_line, confidence=leg.confidence, notes_json=json.dumps(leg.notes), event_id=leg.event_id, event_label=leg.event_label, event_start_time=leg.event_start_time, matched_by=leg.matched_by, settlement=item.settlement, actual_value=item.actual_value, reason=item.reason))
    detail = f'Overall result: {result.overall}'
    if posted_at:
        detail += f' | posted_at={posted_at.isoformat()}'
    if source_type or source_ref:
        detail += f' | source_type={source_type} | source_ref={source_ref}'
    if stake_amount is not None:
        detail += f' | stake={stake_amount}'
    if to_win_amount is not None:
        detail += f' | to_win={to_win_amount}'
    if american_odds is not None:
        detail += f' | american_odds={american_odds}'
    if decimal_odds is not None:
        detail += f' | decimal_odds={decimal_odds}'
    if bookmaker:
        detail += f' | bookmaker={bookmaker}'
    if duplicate:
        detail += f' | duplicate_of={duplicate.id}'
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='ticket_graded', detail=detail))
    db.commit()
    db.refresh(ticket)
    return ticket


def enqueue_review_if_needed(db: Session, ticket: TicketORM, result: GradeResponse, ocr_confidence: float | None = None) -> ReviewQueueORM | None:
    reasons: list[tuple[str, str, str]] = []
    unmatched_count = sum(1 for item in result.legs if item.settlement == 'unmatched')
    if result.overall == 'needs_review':
        reasons.append(('unmatched_legs', 'high' if unmatched_count >= 2 else 'normal', f'{unmatched_count} leg(s) need manual review'))
    if ocr_confidence is not None and ocr_confidence < 0.65:
        reasons.append(('low_ocr_confidence', 'high' if ocr_confidence < 0.4 else 'normal', f'OCR confidence {ocr_confidence:.2f} is below threshold'))
    if not reasons:
        return None
    reason_code, priority, summary = reasons[0]
    existing = db.scalar(select(ReviewQueueORM).where(ReviewQueueORM.ticket_id == ticket.id, ReviewQueueORM.status == 'open'))
    if existing:
        return existing
    item = ReviewQueueORM(ticket_id=ticket.id, status='open', priority=priority, reason_code=reason_code, summary=summary)
    db.add(item)
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='review_enqueued', detail=f'{reason_code}: {summary}'))
    db.commit()
    db.refresh(item)
    return item


def list_review_items(db: Session, status: str = 'open') -> list[ReviewQueueORM]:
    stmt = select(ReviewQueueORM).order_by(ReviewQueueORM.created_at.desc(), ReviewQueueORM.id.desc())
    if status != 'all':
        stmt = stmt.where(ReviewQueueORM.status == status)
    return list(db.scalars(stmt).all())


def resolve_review_item(db: Session, review_id: int, status: str, resolution_note: str) -> ReviewQueueORM | None:
    item = db.get(ReviewQueueORM, review_id)
    if not item:
        return None
    item.status = status
    item.resolution_note = resolution_note
    item.resolved_at = datetime.utcnow()
    db.add(AuditLogORM(ticket_id=item.ticket_id, event_type='review_resolved', detail=f'{status}: {resolution_note}'))
    db.commit()
    db.refresh(item)
    return item


def get_ticket(db: Session, ticket_id: str) -> TicketORM | None:
    return db.get(TicketORM, ticket_id)


def upsert_watched_account(db: Session, username: str, poll_interval_minutes: int = 15, is_enabled: bool = True) -> WatchedAccountORM:
    username_key = username.lower().lstrip('@').strip()
    existing = db.scalar(select(WatchedAccountORM).where(func.lower(WatchedAccountORM.username) == username_key))
    if existing:
        existing.poll_interval_minutes = poll_interval_minutes
        existing.is_enabled = is_enabled
        db.commit()
        db.refresh(existing)
        return existing
    row = WatchedAccountORM(username=username_key, poll_interval_minutes=poll_interval_minutes, is_enabled=is_enabled)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_watched_accounts(db: Session) -> list[WatchedAccountORM]:
    return list(db.scalars(select(WatchedAccountORM).order_by(WatchedAccountORM.created_at.desc(), WatchedAccountORM.id.desc())).all())


def update_watched_account_poll_state(db: Session, account: WatchedAccountORM, source_ref: str | None = None) -> WatchedAccountORM:
    account.last_polled_at = datetime.utcnow()
    if source_ref:
        account.last_seen_source_ref = source_ref
    db.commit()
    db.refresh(account)
    return account


def create_poll_run(db: Session, username: str, watched_account_id: int | None = None, status: str = 'success', fetched_count: int = 0, saved_count: int = 0, detail: str | None = None) -> PollRunORM:
    row = PollRunORM(watched_account_id=watched_account_id, username=username, status=status, fetched_count=fetched_count, saved_count=saved_count, detail=detail)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_poll_runs(db: Session, limit: int = 25) -> list[PollRunORM]:
    return list(db.scalars(select(PollRunORM).order_by(PollRunORM.created_at.desc(), PollRunORM.id.desc()).limit(limit)).all())


def upsert_poll_run(db: Session, row: PollRunORM) -> PollRunORM:
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_aliases(db: Session, alias_type: str | None = None) -> list[AliasOverrideORM]:
    stmt = select(AliasOverrideORM).order_by(AliasOverrideORM.created_at.desc(), AliasOverrideORM.id.desc())
    if alias_type:
        stmt = stmt.where(AliasOverrideORM.alias_type == alias_type)
    return list(db.scalars(stmt).all())


def upsert_alias(db: Session, alias_type: str, alias: str, canonical_value: str, created_by: str | None = None) -> AliasOverrideORM:
    alias_key = alias.strip().lower()
    existing = db.scalar(select(AliasOverrideORM).where(AliasOverrideORM.alias_type == alias_type, func.lower(AliasOverrideORM.alias) == alias_key))
    if existing:
        existing.canonical_value = canonical_value
        existing.created_by = created_by
        db.commit()
        db.refresh(existing)
        return existing
    row = AliasOverrideORM(alias_type=alias_type, alias=alias_key, canonical_value=canonical_value, created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def compute_capper_roi_dashboard(db: Session, username: str | None = None, include_hidden: bool = False, public_only: bool = False) -> list[dict]:
    stmt = select(TicketORM).where(TicketORM.source_type == 'tweet', TicketORM.duplicate_of_ticket_id.is_(None), TicketORM.stake_amount.is_not(None))
    if not include_hidden:
        stmt = stmt.where(TicketORM.is_hidden == False)
    if username:
        username_key = username.lower().lstrip('@').strip()
        stmt = stmt.where(func.lower(TicketORM.source_ref).like(f'%/{username_key}/status/%'))
    tickets = list(db.scalars(stmt).all())
    buckets: dict[str, dict] = {}
    for ticket in tickets:
        source_ref = ticket.source_ref or ''
        capper = source_ref.split('/status/')[0].split('/')[-1] if '/status/' in source_ref else (source_ref.split(':', 1)[0] if ':' in source_ref else source_ref or 'unknown')
        row = buckets.setdefault(capper, {'username': capper, 'settled_with_stake': 0, 'wins_with_stake': 0, 'losses_with_stake': 0, 'total_staked': 0.0, 'total_profit': 0.0, 'roi': 0.0, 'avg_stake': 0.0})
        if ticket.overall not in {'cashed', 'lost'} or ticket.stake_amount is None:
            continue
        row['settled_with_stake'] += 1
        row['total_staked'] += float(ticket.stake_amount)
        row['total_profit'] += float(ticket.profit_amount or 0.0)
        if ticket.overall == 'cashed':
            row['wins_with_stake'] += 1
        else:
            row['losses_with_stake'] += 1
    results = []
    for row in buckets.values():
        total_staked = row['total_staked']
        row['roi'] = round((row['total_profit'] / total_staked) if total_staked else 0.0, 4)
        row['avg_stake'] = round((total_staked / row['settled_with_stake']) if row['settled_with_stake'] else 0.0, 2)
        row['total_staked'] = round(total_staked, 2)
        row['total_profit'] = round(row['total_profit'], 2)
        results.append(row)
    if public_only:
        profiles = {row.username: row for row in db.scalars(select(CapperProfileORM)).all()}
        results = [row for row in results if profiles.get(row['username']) is None or profiles[row['username']].is_public]
    results.sort(key=lambda item: (-item['roi'], -item['total_profit'], item['username']))
    return results





def list_capper_profiles(db: Session) -> list[CapperProfileORM]:
    return list(db.scalars(select(CapperProfileORM).order_by(CapperProfileORM.username.asc())).all())


def get_capper_profile(db: Session, username: str) -> CapperProfileORM | None:
    username_key = username.lower().lstrip('@').strip()
    return db.scalar(select(CapperProfileORM).where(func.lower(CapperProfileORM.username) == username_key))


def create_capper_profile(db: Session, username: str, display_name: str | None = None, bio: str | None = None, is_public: bool = True, moderation_note: str | None = None) -> CapperProfileORM:
    username_key = username.lower().lstrip('@').strip()
    existing = get_capper_profile(db, username_key)
    if existing:
        raise ValueError('Capper profile already exists')
    row = CapperProfileORM(username=username_key, is_public=is_public, moderation_note=moderation_note, display_name=(display_name.strip() or None) if display_name else None, bio=(bio.strip() or None) if bio else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_capper_profile_admin(db: Session, username: str, display_name: str | None = None, bio: str | None = None, is_public: bool | None = None, moderation_note: str | None = None) -> CapperProfileORM:
    row = get_or_create_capper_profile(db, username)
    if display_name is not None:
        row.display_name = display_name.strip() or None
    if bio is not None:
        row.bio = bio.strip() or None
    if is_public is not None:
        row.is_public = is_public
    if moderation_note is not None:
        row.moderation_note = moderation_note.strip() or None
    db.commit()
    db.refresh(row)
    return row

def get_or_create_capper_profile(db: Session, username: str) -> CapperProfileORM:
    username_key = username.lower().lstrip('@').strip()
    existing = db.scalar(select(CapperProfileORM).where(func.lower(CapperProfileORM.username) == username_key))
    if existing:
        return existing
    row = CapperProfileORM(username=username_key, is_public=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_capper_profile_visibility(db: Session, username: str, is_public: bool, moderation_note: str | None = None) -> CapperProfileORM:
    row = get_or_create_capper_profile(db, username)
    row.is_public = is_public
    row.moderation_note = moderation_note
    db.commit()
    db.refresh(row)
    return row


def hide_ticket(db: Session, ticket: TicketORM, reason: str | None = None) -> TicketORM:
    ticket.is_hidden = True
    ticket.hidden_reason = reason
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='ticket_hidden', detail=reason or 'hidden by moderator'))
    db.commit()
    db.refresh(ticket)
    return ticket


def unhide_ticket(db: Session, ticket: TicketORM) -> TicketORM:
    ticket.is_hidden = False
    ticket.hidden_reason = None
    db.add(AuditLogORM(ticket_id=ticket.id, event_type='ticket_unhidden', detail='ticket restored by moderator'))
    db.commit()
    db.refresh(ticket)
    return ticket


def list_hidden_tickets(db: Session) -> list[TicketORM]:
    return list(db.scalars(select(TicketORM).where(TicketORM.is_hidden == True).order_by(TicketORM.created_at.desc(), TicketORM.id.desc())).all())



def get_user_by_username(db: Session, username: str) -> UserORM | None:
    username_key = username.lower().lstrip('@').strip()
    return db.scalar(select(UserORM).where(func.lower(UserORM.username) == username_key))


def create_user(db: Session, username: str, password_hash: str, email: str | None = None, is_admin: bool = False, role: str = 'member', linked_capper_username: str | None = None) -> UserORM:
    username_key = username.lower().lstrip('@').strip()
    normalized_role = 'admin' if is_admin else (role or 'member').lower().strip()
    row = UserORM(username=username_key, email=(email.lower().strip() if email else None), password_hash=password_hash, is_admin=is_admin, role=normalized_role, linked_capper_username=(linked_capper_username.lower().lstrip('@').strip() if linked_capper_username else None))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_user_session(db: Session, user: UserORM, session_token: str, expires_at: datetime | None = None) -> UserSessionORM:
    row = UserSessionORM(user_id=user.id, session_token=session_token, expires_at=expires_at, last_seen_at=datetime.utcnow(), is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_user_session(db: Session, session_token: str) -> bool:
    row = db.scalar(select(UserSessionORM).where(UserSessionORM.session_token == session_token, UserSessionORM.is_active == True))
    if not row:
        return False
    row.is_active = False
    db.commit()
    return True


def list_admin_sessions(db: Session) -> list[UserSessionORM]:
    stmt = select(UserSessionORM).join(UserORM).where(UserORM.is_admin == True).order_by(UserSessionORM.created_at.desc(), UserSessionORM.id.desc())
    return list(db.scalars(stmt).all())


def set_user_role(db: Session, user: UserORM, role: str, linked_capper_username: str | None = None) -> UserORM:
    normalized_role = role.lower().strip()
    user.role = normalized_role
    user.is_admin = normalized_role == 'admin'
    user.linked_capper_username = linked_capper_username.lower().lstrip('@').strip() if linked_capper_username else None
    db.commit()
    db.refresh(user)
    return user


def claim_capper_profile(db: Session, user: UserORM, capper_username: str) -> CapperProfileORM:
    profile = get_or_create_capper_profile(db, capper_username)
    profile.claimed_by_user_id = user.id
    if not profile.display_name:
        profile.display_name = capper_username.lower().lstrip('@').strip()
    db.commit()
    db.refresh(profile)
    return profile


def update_capper_profile_self(db: Session, user: UserORM, display_name: str | None = None, bio: str | None = None, is_public: bool | None = None) -> CapperProfileORM:
    if not user.linked_capper_username:
        raise ValueError('No linked capper profile')
    profile = get_or_create_capper_profile(db, user.linked_capper_username)
    if profile.claimed_by_user_id and profile.claimed_by_user_id != user.id and not user.is_admin:
        raise ValueError('Capper profile already claimed by another user')
    profile.claimed_by_user_id = user.id
    if display_name is not None:
        profile.display_name = display_name.strip() or None
    if bio is not None:
        profile.bio = bio.strip() or None
    if is_public is not None:
        profile.is_public = is_public
    db.commit()
    db.refresh(profile)
    return profile


def seed_subscription_plans(db: Session) -> None:
    defaults = [
        ('free', 'Free', 0.0, ['Public leaderboards', 'Basic slip grading']),
        ('pro', 'Pro', 19.0, ['Public leaderboards', 'Basic slip grading', 'ROI dashboard', 'Tracked cappers', 'Priority review tools']),
        ('pro_plus', 'Pro Plus', 49.0, ['Public leaderboards', 'Basic slip grading', 'ROI dashboard', 'Tracked cappers', 'Priority review tools', 'API access', 'White-label exports']),
    ]
    existing = {row.code: row for row in db.scalars(select(SubscriptionPlanORM)).all()}
    changed = False
    for code, name, price, features in defaults:
        row = existing.get(code)
        if row is None:
            db.add(SubscriptionPlanORM(code=code, name=name, price_monthly=price, features_json=json.dumps(features), is_active=True))
            changed = True
        else:
            row.name = name
            row.price_monthly = price
            row.features_json = json.dumps(features)
            row.is_active = True
            changed = True
    if changed:
        db.commit()


def list_subscription_plans(db: Session) -> list[SubscriptionPlanORM]:
    seed_subscription_plans(db)
    return list(db.scalars(select(SubscriptionPlanORM).where(SubscriptionPlanORM.is_active == True).order_by(SubscriptionPlanORM.price_monthly.asc(), SubscriptionPlanORM.id.asc())).all())


def get_active_subscription(db: Session, user: UserORM) -> UserSubscriptionORM | None:
    return db.scalar(select(UserSubscriptionORM).where(UserSubscriptionORM.user_id == user.id, UserSubscriptionORM.status.in_(['pending','active','trialing'])).order_by(UserSubscriptionORM.created_at.desc(), UserSubscriptionORM.id.desc()))


def get_effective_plan_code(db: Session, user: UserORM) -> str:
    sub = get_active_subscription(db, user)
    if not sub or sub.status not in {'active', 'trialing'}:
        return 'free'
    return sub.plan_code or 'free'


def get_plan_entitlements(plan_code: str) -> list[str]:
    mapping = {
        'free': ['basic_grading', 'public_leaderboards'],
        'pro': ['basic_grading', 'public_leaderboards', 'roi_dashboard', 'review_queue', 'tracked_cappers'],
        'pro_plus': ['basic_grading', 'public_leaderboards', 'roi_dashboard', 'review_queue', 'tracked_cappers', 'api_access', 'white_label_exports'],
    }
    return mapping.get(plan_code, mapping['free'])


def get_user_entitlements(db: Session, user: UserORM) -> dict[str, object]:
    plan_code = get_effective_plan_code(db, user)
    return {
        'plan_code': plan_code,
        'is_active': plan_code != 'free',
        'entitlements': get_plan_entitlements(plan_code),
    }


def user_has_entitlement(db: Session, user: UserORM, entitlement: str) -> bool:
    return entitlement in get_user_entitlements(db, user)['entitlements']


def create_stripe_checkout(db: Session, user: UserORM, plan_code: str, success_url: str | None = None, cancel_url: str | None = None) -> tuple[UserSubscriptionORM, str]:
    row = create_subscription_checkout(db, user, plan_code=plan_code, provider='stripe')
    success = success_url or 'https://example.com/billing/success'
    cancel = cancel_url or 'https://example.com/billing/cancel'
    result = create_checkout_session(plan_code=plan_code, success_url=success, cancel_url=cancel, customer_email=user.email, customer_id=row.provider_customer_id)
    row.provider_checkout_id = result.checkout_id
    row.provider_customer_id = result.customer_id or row.provider_customer_id
    row.provider_subscription_id = result.subscription_id or row.provider_subscription_id
    db.commit()
    db.refresh(row)
    return row, result.checkout_url


def create_subscription_checkout(db: Session, user: UserORM, plan_code: str, provider: str = 'mock_stripe') -> UserSubscriptionORM:
    seed_subscription_plans(db)
    plan = db.scalar(select(SubscriptionPlanORM).where(SubscriptionPlanORM.code == plan_code, SubscriptionPlanORM.is_active == True))
    if not plan:
        raise ValueError('Unknown plan')
    existing = get_active_subscription(db, user)
    if existing and existing.status in {'pending','active','trialing'}:
        existing.status = 'canceled'
    checkout_id = f'chk_{secrets.token_hex(8)}'
    row = UserSubscriptionORM(user_id=user.id, plan_code=plan.code, status='pending' if plan.price_monthly > 0 else 'active', provider=provider, provider_checkout_id=checkout_id, started_at=datetime.utcnow() if plan.price_monthly == 0 else None, current_period_end=(datetime.utcnow() + timedelta(days=30)) if plan.price_monthly == 0 else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def activate_subscription_checkout(db: Session, subscription_id: int) -> UserSubscriptionORM | None:
    row = db.get(UserSubscriptionORM, subscription_id)
    if not row:
        return None
    row.status = 'active'
    row.started_at = datetime.utcnow()
    row.current_period_end = datetime.utcnow() + timedelta(days=30)
    row.cancel_at_period_end = False
    if not row.provider_customer_id:
        row.provider_customer_id = f'cus_{secrets.token_hex(6)}'
    if not row.provider_subscription_id:
        row.provider_subscription_id = f'sub_{secrets.token_hex(6)}'
    db.commit()
    db.refresh(row)
    return row


def cancel_user_subscription(db: Session, user: UserORM, immediate: bool = False) -> UserSubscriptionORM | None:
    sub = get_active_subscription(db, user)
    if sub is None:
        return None
    if immediate:
        sub.status = 'canceled'
        sub.cancel_at_period_end = False
        sub.current_period_end = datetime.utcnow()
    else:
        sub.cancel_at_period_end = True
        if sub.status == 'pending':
            sub.status = 'active'
            sub.started_at = sub.started_at or datetime.utcnow()
            sub.current_period_end = sub.current_period_end or (datetime.utcnow() + timedelta(days=30))
    db.commit()
    db.refresh(sub)
    return sub


def resume_user_subscription(db: Session, user: UserORM) -> UserSubscriptionORM | None:
    sub = get_active_subscription(db, user)
    if sub is None:
        return None
    if sub.status in {'canceled', 'expired'}:
        return None
    sub.cancel_at_period_end = False
    if sub.status == 'past_due':
        sub.status = 'active'
    sub.current_period_end = sub.current_period_end or (datetime.utcnow() + timedelta(days=30))
    db.commit()
    db.refresh(sub)
    return sub


def create_billing_portal_link(db: Session, user: UserORM, return_url: str | None = None) -> tuple[UserSubscriptionORM | None, str]:
    sub = get_active_subscription(db, user)
    if sub is None:
        return None, return_url or 'https://example.com/app'
    result = create_billing_portal(customer_id=sub.provider_customer_id, return_url=(return_url or 'https://example.com/app'))
    if result.customer_id and not sub.provider_customer_id:
        sub.provider_customer_id = result.customer_id
        db.commit()
        db.refresh(sub)
    return sub, result.portal_url


def get_billing_account_summary(db: Session, user: UserORM) -> dict[str, object]:
    sub = get_active_subscription(db, user)
    plans = list_subscription_plans(db)
    recent_events = list(db.scalars(select(StripeEventORM).order_by(StripeEventORM.processed_at.desc()).limit(5)).all())
    invoices = list_billing_invoices(db, user=user, limit=5)
    emails = list_email_notifications(db, user=user, limit=5)
    return {
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role or ('admin' if user.is_admin else 'member'),
            'linked_capper_username': user.linked_capper_username,
        },
        'subscription': sub,
        'entitlements': get_user_entitlements(db, user),
        'plans': plans,
        'recent_billing_events': recent_events,
        'recent_invoices': invoices,
        'recent_email_notifications': emails,
    }


def apply_stripe_event(db: Session, event_id: str, event_type: str, payload: dict) -> tuple[bool, UserSubscriptionORM | None]:
    existing = db.scalar(select(StripeEventORM).where(StripeEventORM.stripe_event_id == event_id))
    if existing is not None:
        return False, None
    db.add(StripeEventORM(stripe_event_id=event_id, event_type=event_type, payload_json=json.dumps(payload, default=str)))
    obj = payload.get('data', {}).get('object', {}) if isinstance(payload, dict) else {}
    target_checkout_id = obj.get('provider_checkout_id') or obj.get('checkout_id') or obj.get('client_reference_id')
    sub = None
    if target_checkout_id:
        sub = db.scalar(select(UserSubscriptionORM).where(UserSubscriptionORM.provider_checkout_id == target_checkout_id))
    if sub is None and obj.get('subscription'):
        sub = db.scalar(select(UserSubscriptionORM).where(UserSubscriptionORM.provider_subscription_id == obj.get('subscription')))
    if sub is None and obj.get('customer'):
        sub = db.scalar(select(UserSubscriptionORM).where(UserSubscriptionORM.provider_customer_id == obj.get('customer')).order_by(UserSubscriptionORM.created_at.desc(), UserSubscriptionORM.id.desc()))
    if sub is not None and event_type in {'checkout.session.completed', 'invoice.paid'}:
        sub.status = 'active'
        sub.provider = 'stripe'
        sub.started_at = sub.started_at or datetime.utcnow()
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)
        sub.cancel_at_period_end = False
        sub.provider_customer_id = obj.get('customer') or sub.provider_customer_id
        sub.provider_subscription_id = obj.get('subscription') or sub.provider_subscription_id
    elif sub is not None and event_type in {'customer.subscription.deleted', 'invoice.payment_failed'}:
        sub.status = 'canceled' if event_type == 'customer.subscription.deleted' else 'past_due'
        if event_type == 'customer.subscription.deleted':
            sub.cancel_at_period_end = False

    if sub is not None and event_type == 'checkout.session.completed':
        _send_subscription_email(db, sub, template_key='subscription_activated', event_type=event_type, subject=f'{sub.plan_code.title()} subscription active')
    elif sub is not None and event_type == 'invoice.paid':
        amount = float(obj.get('amount_paid') or obj.get('amount_due') or 0) / 100.0 if float(obj.get('amount_paid') or obj.get('amount_due') or 0) > 1000 else float(obj.get('amount_paid') or obj.get('amount_due') or 0)
        record_billing_invoice(
            db,
            user_id=sub.user_id,
            subscription_id=sub.id,
            invoice_id=(obj.get('id') or f'inv_{event_id}'),
            provider_invoice_id=obj.get('id'),
            status='paid',
            amount_paid=amount,
            currency=(obj.get('currency') or 'usd'),
            hosted_invoice_url=obj.get('hosted_invoice_url'),
            period_start=_coerce_unix_or_dt(obj.get('period_start')),
            period_end=_coerce_unix_or_dt(obj.get('period_end')),
            paid_at=_coerce_unix_or_dt(obj.get('status_transitions', {}).get('paid_at')) or datetime.utcnow(),
        )
        _send_subscription_email(db, sub, template_key='invoice_paid', event_type=event_type, subject=f'Payment received for {sub.plan_code.title()}')
    elif sub is not None and event_type == 'invoice.payment_failed':
        _send_subscription_email(db, sub, template_key='invoice_payment_failed', event_type=event_type, subject=f'Payment failed for {sub.plan_code.title()}')
    elif sub is not None and event_type == 'customer.subscription.deleted':
        _send_subscription_email(db, sub, template_key='subscription_canceled', event_type=event_type, subject=f'{sub.plan_code.title()} subscription canceled')
    db.commit()
    if sub is not None:
        db.refresh(sub)
    return True, sub


def record_affiliate_click(db: Session, bookmaker: str, resolved_url: str, affiliate_link: AffiliateLinkORM | None = None, capper_username: str | None = None, ticket_id: str | None = None, source: str | None = None, metadata: dict | None = None) -> AffiliateClickORM:
    row = AffiliateClickORM(
        bookmaker=bookmaker.lower().strip(),
        resolved_url=resolved_url,
        affiliate_link_id=affiliate_link.id if affiliate_link else None,
        capper_username=(capper_username.lower().lstrip('@') if capper_username else None),
        ticket_id=ticket_id,
        source=source,
        click_token=secrets.token_hex(16),
        metadata_json=json.dumps(metadata or {}, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def affiliate_analytics(db: Session, bookmaker: str | None = None) -> list[dict]:
    click_stmt = select(
        AffiliateClickORM.bookmaker.label('bookmaker'),
        func.count(AffiliateClickORM.id).label('clicks'),
        func.count(func.distinct(AffiliateClickORM.capper_username)).label('unique_cappers'),
        func.max(AffiliateClickORM.created_at).label('latest_click_at'),
    )
    if bookmaker:
        click_stmt = click_stmt.where(func.lower(AffiliateClickORM.bookmaker) == bookmaker.lower().strip())
    click_stmt = click_stmt.group_by(AffiliateClickORM.bookmaker)
    clicks = {row.bookmaker: row for row in db.execute(click_stmt).all()}

    conv_stmt = select(
        AffiliateConversionORM.bookmaker.label('bookmaker'),
        func.count(AffiliateConversionORM.id).label('conversions'),
        func.coalesce(func.sum(AffiliateConversionORM.revenue_amount), 0.0).label('revenue'),
    )
    if bookmaker:
        conv_stmt = conv_stmt.where(func.lower(AffiliateConversionORM.bookmaker) == bookmaker.lower().strip())
    conv_stmt = conv_stmt.group_by(AffiliateConversionORM.bookmaker)
    conversions = {row.bookmaker: row for row in db.execute(conv_stmt).all()}

    keys = sorted(set(clicks) | set(conversions))
    rows = []
    for key in keys:
        click_row = clicks.get(key)
        conv_row = conversions.get(key)
        click_count = int(getattr(click_row, 'clicks', 0) or 0)
        conv_count = int(getattr(conv_row, 'conversions', 0) or 0)
        revenue = float(getattr(conv_row, 'revenue', 0.0) or 0.0)
        rows.append({
            'bookmaker': key,
            'clicks': click_count,
            'conversions': conv_count,
            'conversion_rate': (conv_count / click_count) if click_count else 0.0,
            'revenue': revenue,
            'unique_cappers': int(getattr(click_row, 'unique_cappers', 0) or 0),
            'latest_click_at': getattr(click_row, 'latest_click_at', None),
        })
    rows.sort(key=lambda r: (-r['clicks'], r['bookmaker']))
    return rows


def list_affiliate_links(db: Session) -> list[AffiliateLinkORM]:
    return list(db.scalars(select(AffiliateLinkORM).order_by(AffiliateLinkORM.bookmaker.asc())).all())


def upsert_affiliate_link(db: Session, bookmaker: str, base_url: str, affiliate_code: str | None = None, campaign_code: str | None = None, is_active: bool = True) -> AffiliateLinkORM:
    key = bookmaker.lower().strip()
    row = db.scalar(select(AffiliateLinkORM).where(func.lower(AffiliateLinkORM.bookmaker) == key))
    if row is None:
        row = AffiliateLinkORM(bookmaker=key, base_url=base_url.strip(), affiliate_code=affiliate_code, campaign_code=campaign_code, is_active=is_active)
        db.add(row)
    else:
        row.base_url = base_url.strip()
        row.affiliate_code = affiliate_code
        row.campaign_code = campaign_code
        row.is_active = is_active
    db.commit()
    db.refresh(row)
    return row


def resolve_affiliate_url(db: Session, bookmaker: str, capper_username: str | None = None, ticket_id: str | None = None, source: str = 'parlaybot') -> tuple[str, AffiliateLinkORM | None, AffiliateClickORM]:
    key = bookmaker.lower().strip()
    row = db.scalar(select(AffiliateLinkORM).where(func.lower(AffiliateLinkORM.bookmaker) == key, AffiliateLinkORM.is_active == True))
    if row is None:
        fallback = f'https://sportsbook.example/{key}'
        qs = urlencode({'src': source, 'capper': capper_username or '', 'ticket_id': ticket_id or ''})
        url = f'{fallback}?{qs}'
        click = record_affiliate_click(db, key, url, affiliate_link=None, capper_username=capper_username, ticket_id=ticket_id, source=source, metadata={'fallback': True})
        return url, None, click
    params = {'src': source}
    if row.affiliate_code:
        params['aff'] = row.affiliate_code
    if row.campaign_code:
        params['campaign'] = row.campaign_code
    if capper_username:
        params['capper'] = capper_username.lower().lstrip('@')
    if ticket_id:
        params['ticket_id'] = ticket_id
    sep = '&' if '?' in row.base_url else '?'
    url = row.base_url + sep + urlencode(params)
    click = record_affiliate_click(db, key, url, affiliate_link=row, capper_username=capper_username, ticket_id=ticket_id, source=source, metadata={'campaign_code': row.campaign_code})
    return url, row, click


def set_capper_verification(db: Session, username: str, verified: bool, badge: str | None = None, note: str | None = None) -> CapperProfileORM:
    row = get_or_create_capper_profile(db, username)
    row.is_verified = verified
    row.verification_badge = (badge or 'verified') if verified else None
    row.verification_note = note if verified else None
    db.commit()
    db.refresh(row)
    return row


def _coerce_unix_or_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value)
        except Exception:
            return None
    return None


def record_billing_invoice(db: Session, *, user_id: int | None, subscription_id: int | None, invoice_id: str, provider_invoice_id: str | None = None, status: str = 'paid', amount_paid: float = 0.0, currency: str = 'usd', hosted_invoice_url: str | None = None, period_start: datetime | None = None, period_end: datetime | None = None, paid_at: datetime | None = None) -> BillingInvoiceORM:
    row = db.scalar(select(BillingInvoiceORM).where(BillingInvoiceORM.invoice_id == invoice_id))
    if row is None and provider_invoice_id:
        row = db.scalar(select(BillingInvoiceORM).where(BillingInvoiceORM.provider_invoice_id == provider_invoice_id))
    if row is None:
        row = BillingInvoiceORM(
            invoice_id=invoice_id,
            provider_invoice_id=provider_invoice_id,
            user_id=user_id,
            subscription_id=subscription_id,
            status=status,
            amount_paid=amount_paid,
            currency=currency.lower(),
            hosted_invoice_url=hosted_invoice_url,
            pdf_download_token=secrets.token_urlsafe(18),
            pdf_filename=f'{invoice_id}.pdf',
            pdf_generated_at=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
            paid_at=paid_at,
        )
        db.add(row)
    else:
        row.user_id = user_id or row.user_id
        row.subscription_id = subscription_id or row.subscription_id
        row.provider_invoice_id = provider_invoice_id or row.provider_invoice_id
        row.status = status
        row.amount_paid = amount_paid
        row.currency = currency.lower()
        row.hosted_invoice_url = hosted_invoice_url or row.hosted_invoice_url
        row.period_start = period_start or row.period_start
        row.period_end = period_end or row.period_end
        row.paid_at = paid_at or row.paid_at
        row.pdf_download_token = row.pdf_download_token or secrets.token_urlsafe(18)
        row.pdf_filename = row.pdf_filename or f'{row.invoice_id}.pdf'
        row.pdf_generated_at = row.pdf_generated_at or datetime.utcnow()
    db.flush()
    return row


def _send_subscription_email(db: Session, sub: UserSubscriptionORM, *, template_key: str, event_type: str, subject: str) -> EmailNotificationORM | None:
    user = db.get(UserORM, sub.user_id) if sub.user_id else None
    to_email = user.email if user and user.email else None
    if not to_email:
        return None
    payload = {'plan_code': sub.plan_code, 'subscription_id': sub.id, 'username': user.username if user else None}
    send_result = send_email_message(to_email=to_email, subject=subject, body_text=f"{subject}\n\nPlan: {sub.plan_code}\nSubscription ID: {sub.id}", body_html=None)
    row = EmailNotificationORM(user_id=user.id, subscription_id=sub.id, to_email=to_email, template_key=template_key, event_type=event_type, subject=subject, body_json=json.dumps(payload, default=str), provider=send_result.provider, provider_message_id=send_result.message_id, status=send_result.status, sent_at=(datetime.utcnow() if send_result.status in {'sent','queued'} else None))
    db.add(row)
    db.flush()
    return row


def get_billing_invoice_for_user(db: Session, invoice_id: str, user: UserORM) -> BillingInvoiceORM | None:
    return db.scalar(select(BillingInvoiceORM).where(BillingInvoiceORM.invoice_id == invoice_id, BillingInvoiceORM.user_id == user.id))


def build_invoice_download_url(invoice: BillingInvoiceORM, *, base_path: str = '/billing/invoices') -> str:
    query = urlencode({'token': invoice.pdf_download_token}) if invoice.pdf_download_token else ''
    suffix = f'?{query}' if query else ''
    return f'{base_path}/{invoice.invoice_id}/download{suffix}'


def _invoice_signing_secret() -> str:
    import os
    return os.getenv('INVOICE_LINK_SECRET', 'dev-invoice-link-secret')


def build_signed_invoice_url(invoice: BillingInvoiceORM, *, base_path: str = '/public/invoices', expires_at: datetime | None = None) -> tuple[str, datetime]:
    expires_at = expires_at or (datetime.utcnow() + timedelta(hours=24))
    expires_ts = int(expires_at.timestamp())
    message = f"{invoice.invoice_id}:{invoice.pdf_download_token or ''}:{expires_ts}".encode('utf-8')
    sig = hmac.new(_invoice_signing_secret().encode('utf-8'), message, hashlib.sha256).hexdigest()
    query = urlencode({'token': invoice.pdf_download_token or '', 'expires': expires_ts, 'sig': sig})
    return f'{base_path}/{invoice.invoice_id}?{query}', expires_at


def verify_signed_invoice_access(invoice: BillingInvoiceORM, *, token: str | None, expires: int | str | None, sig: str | None) -> bool:
    if not token or not sig or expires is None:
        return False
    try:
        expires_ts = int(expires)
    except Exception:
        return False
    if expires_ts < int(datetime.utcnow().timestamp()):
        return False
    expected_message = f"{invoice.invoice_id}:{invoice.pdf_download_token or ''}:{expires_ts}".encode('utf-8')
    expected_sig = hmac.new(_invoice_signing_secret().encode('utf-8'), expected_message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig) and token == (invoice.pdf_download_token or '')


def render_invoice_pdf(invoice: BillingInvoiceORM, user: UserORM | None = None) -> bytes:
    return render_invoice_pdf_bytes(
        invoice_id=invoice.invoice_id,
        provider_invoice_id=invoice.provider_invoice_id,
        username=(user.username if user else None),
        email=(user.email if user else None),
        amount_paid=invoice.amount_paid,
        currency=invoice.currency,
        status=invoice.status,
        paid_at=invoice.paid_at,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        hosted_invoice_url=invoice.hosted_invoice_url,
    )


def list_billing_invoices(db: Session, *, user: UserORM | None = None, limit: int = 50) -> list[BillingInvoiceORM]:
    stmt = select(BillingInvoiceORM).order_by(BillingInvoiceORM.created_at.desc(), BillingInvoiceORM.id.desc()).limit(limit)
    if user is not None:
        stmt = stmt.where(BillingInvoiceORM.user_id == user.id)
    return list(db.scalars(stmt).all())


def list_email_notifications(db: Session, *, user: UserORM | None = None, limit: int = 50) -> list[EmailNotificationORM]:
    stmt = select(EmailNotificationORM).order_by(EmailNotificationORM.created_at.desc(), EmailNotificationORM.id.desc()).limit(limit)
    if user is not None:
        stmt = stmt.where(EmailNotificationORM.user_id == user.id)
    return list(db.scalars(stmt).all())


def record_affiliate_conversion(db: Session, *, click_token: str, bookmaker: str | None = None, revenue_amount: float | None = None, currency: str = 'usd', external_ref: str | None = None, metadata: dict | None = None) -> AffiliateConversionORM:
    existing = None
    if external_ref:
        existing = db.scalar(select(AffiliateConversionORM).where(AffiliateConversionORM.external_ref == external_ref))
        if existing is not None:
            return existing
    click = db.scalar(select(AffiliateClickORM).where(AffiliateClickORM.click_token == click_token))
    bm = (bookmaker or (click.bookmaker if click else None) or 'unknown').lower().strip()
    row = AffiliateConversionORM(click_id=(click.id if click else None), click_token=click_token, bookmaker=bm, revenue_amount=float(revenue_amount or 0.0), currency=(currency or 'usd').lower(), external_ref=external_ref, metadata_json=json.dumps(metadata or {}, default=str))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_affiliate_conversions(db: Session, bookmaker: str | None = None, limit: int = 100) -> list[AffiliateConversionORM]:
    stmt = select(AffiliateConversionORM).order_by(AffiliateConversionORM.created_at.desc(), AffiliateConversionORM.id.desc()).limit(limit)
    if bookmaker:
        stmt = stmt.where(func.lower(AffiliateConversionORM.bookmaker) == bookmaker.lower().strip())
    return list(db.scalars(stmt).all())


def record_affiliate_webhook_event(db: Session, *, source_type: str, network: str | None = None, external_ref: str | None = None, click_token: str | None = None, status: str = 'received', conversion_id: int | None = None, payload: dict | None = None) -> AffiliateWebhookEventORM:
    row = AffiliateWebhookEventORM(source_type=source_type, network=network, external_ref=external_ref, click_token=click_token, status=status, conversion_id=conversion_id, payload_json=json.dumps(payload or {}, default=str))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ingest_affiliate_postback(db: Session, *, source_type: str, network: str | None = None, click_token: str | None = None, bookmaker: str | None = None, revenue_amount: float | None = None, currency: str = 'usd', external_ref: str | None = None, metadata: dict | None = None) -> tuple[AffiliateWebhookEventORM, AffiliateConversionORM | None]:
    conversion = None
    status = 'ignored'
    if click_token:
        conversion = record_affiliate_conversion(db, click_token=click_token, bookmaker=bookmaker, revenue_amount=revenue_amount, currency=currency, external_ref=external_ref, metadata=metadata)
        status = 'recorded'
    event = record_affiliate_webhook_event(db, source_type=source_type, network=network, external_ref=external_ref, click_token=click_token, status=status, conversion_id=(conversion.id if conversion else None), payload={
        'bookmaker': bookmaker, 'revenue_amount': revenue_amount, 'currency': currency, 'metadata': metadata or {}
    })
    return event, conversion


def list_affiliate_webhook_events(db: Session, limit: int = 100) -> list[AffiliateWebhookEventORM]:
    stmt = select(AffiliateWebhookEventORM).order_by(AffiliateWebhookEventORM.created_at.desc(), AffiliateWebhookEventORM.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def get_billing_history(db: Session, user: UserORM) -> dict[str, object]:
    return {
        'invoices': list_billing_invoices(db, user=user, limit=50),
        'recent_billing_events': list(db.scalars(select(StripeEventORM).order_by(StripeEventORM.processed_at.desc()).limit(25)).all()),
        'email_notifications': list_email_notifications(db, user=user, limit=50),
    }
