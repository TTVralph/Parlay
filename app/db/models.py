from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TicketORM(Base):
    __tablename__ = 'tickets'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    sport: Mapped[str] = mapped_column(String(20), default='NBA')
    overall: Mapped[str] = mapped_column(String(20), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    bookmaker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stake_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    to_win_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    american_odds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decimal_odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(default=False, nullable=False)
    hidden_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duplicate_of_ticket_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('tickets.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    legs: Mapped[list['TicketLegORM']] = relationship(back_populates='ticket', cascade='all, delete-orphan')
    audit_logs: Mapped[list['AuditLogORM']] = relationship(back_populates='ticket', cascade='all, delete-orphan')
    review_items: Mapped[list['ReviewQueueORM']] = relationship(back_populates='ticket', cascade='all, delete-orphan')
    duplicate_of: Mapped['TicketORM | None'] = relationship(remote_side='TicketORM.id', foreign_keys=[duplicate_of_ticket_id])


class PublicSlipResultORM(Base):
    __tablename__ = 'public_slip_results'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    raw_slip_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_legs_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    legs_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    matched_events_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    overall_result: Mapped[str] = mapped_column(String(20), nullable=False)
    parser_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bet_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    stake_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketLegORM(Base):
    __tablename__ = 'ticket_legs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey('tickets.id', ondelete='CASCADE'), index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    sport: Mapped[str] = mapped_column(String(20), default='NBA')
    market_type: Mapped[str] = mapped_column(String(50), nullable=False)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    player: Mapped[str | None] = mapped_column(String(100), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_line: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    notes_json: Mapped[str] = mapped_column(Text, default='[]')
    event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    matched_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    settlement: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped['TicketORM'] = relationship(back_populates='legs')


class AuditLogORM(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey('tickets.id', ondelete='CASCADE'), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket: Mapped['TicketORM'] = relationship(back_populates='audit_logs')


class ReviewQueueORM(Base):
    __tablename__ = 'review_queue'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey('tickets.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='open', nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default='normal', nullable=False)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ticket: Mapped['TicketORM'] = relationship(back_populates='review_items')


class WatchedAccountORM(Base):
    __tablename__ = 'watched_accounts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_seen_source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PollRunORM(Base):
    __tablename__ = 'poll_runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watched_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('watched_accounts.id', ondelete='SET NULL'), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='success')
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)




class CapperProfileORM(Base):
    __tablename__ = 'capper_profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    is_public: Mapped[bool] = mapped_column(default=True, nullable=False)
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    verification_badge: Mapped[str | None] = mapped_column(String(30), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AliasOverrideORM(Base):
    __tablename__ = 'alias_overrides'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SubscriptionPlanORM(Base):
    __tablename__ = 'subscription_plans'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_monthly: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    features_json: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSubscriptionORM(Base):
    __tablename__ = 'user_subscriptions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default='mock_stripe')
    provider_checkout_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped['UserORM'] = relationship(back_populates='subscriptions')


class AffiliateLinkORM(Base):
    __tablename__ = 'affiliate_links'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    campaign_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)




class AffiliateClickORM(Base):
    __tablename__ = 'affiliate_clicks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resolved_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_link_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('affiliate_links.id', ondelete='SET NULL'), nullable=True, index=True)
    capper_username: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('tickets.id', ondelete='SET NULL'), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    click_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StripeEventORM(Base):
    __tablename__ = 'stripe_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stripe_event_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BillingInvoiceORM(Base):
    __tablename__ = 'billing_invoices'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('user_subscriptions.id', ondelete='SET NULL'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='open')
    amount_paid: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default='usd')
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_download_token: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    pdf_filename: Mapped[str | None] = mapped_column(String(180), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmailNotificationORM(Base):
    __tablename__ = 'email_notifications'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('user_subscriptions.id', ondelete='SET NULL'), nullable=True, index=True)
    to_email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    template_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='sent')
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AffiliateConversionORM(Base):
    __tablename__ = 'affiliate_conversions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    click_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('affiliate_clicks.id', ondelete='SET NULL'), nullable=True, index=True)
    click_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    revenue_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default='usd')
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)




class AffiliateWebhookEventORM(Base):
    __tablename__ = 'affiliate_webhook_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    network: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    click_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='received')
    conversion_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('affiliate_conversions.id', ondelete='SET NULL'), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserORM(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default='member', nullable=False)
    linked_capper_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sessions: Mapped[list['UserSessionORM']] = relationship(back_populates='user', cascade='all, delete-orphan')
    subscriptions: Mapped[list['UserSubscriptionORM']] = relationship(back_populates='user', cascade='all, delete-orphan')


class UserSessionORM(Base):
    __tablename__ = 'user_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    session_token: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    user: Mapped['UserORM'] = relationship(back_populates='sessions')
