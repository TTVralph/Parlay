from __future__ import annotations

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from .migrations import apply_migrations

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./parlay_bot.db')

connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

WATCHED_ACCOUNTS_DDL = """
CREATE TABLE watched_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    is_enabled BOOLEAN NOT NULL DEFAULT 1,
    poll_interval_minutes INTEGER NOT NULL DEFAULT 15,
    last_polled_at DATETIME NULL,
    last_seen_source_ref VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

POLL_RUNS_DDL = """
CREATE TABLE poll_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watched_account_id INTEGER NULL,
    username VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'success',
    fetched_count INTEGER NOT NULL DEFAULT 0,
    saved_count INTEGER NOT NULL DEFAULT 0,
    detail TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(watched_account_id) REFERENCES watched_accounts (id) ON DELETE SET NULL
)
"""

CAPPER_PROFILES_DDL = """
CREATE TABLE capper_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    is_public BOOLEAN NOT NULL DEFAULT 1,
    moderation_note TEXT NULL,
    claimed_by_user_id INTEGER NULL,
    display_name VARCHAR(80) NULL,
    bio TEXT NULL,
    is_verified BOOLEAN NOT NULL DEFAULT 0,
    verification_badge VARCHAR(30) NULL,
    verification_note TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


USERS_DDL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(120) NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

USER_SESSIONS_DDL = """
CREATE TABLE user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_token VARCHAR(120) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL,
    last_seen_at DATETIME NULL,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)
"""


SUBSCRIPTION_PLANS_DDL = """
CREATE TABLE subscription_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(60) NOT NULL,
    price_monthly FLOAT NOT NULL DEFAULT 0,
    features_json TEXT NOT NULL DEFAULT '[]',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

USER_SUBSCRIPTIONS_DDL = """
CREATE TABLE user_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_code VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider VARCHAR(30) NOT NULL DEFAULT 'mock_stripe',
    provider_checkout_id VARCHAR(80) NULL UNIQUE,
    started_at DATETIME NULL,
    current_period_end DATETIME NULL,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)
"""

AFFILIATE_LINKS_DDL = """
CREATE TABLE affiliate_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker VARCHAR(50) NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    affiliate_code VARCHAR(80) NULL,
    campaign_code VARCHAR(80) NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""



AFFILIATE_CLICKS_DDL = """
CREATE TABLE affiliate_clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker VARCHAR(50) NOT NULL,
    resolved_url TEXT NOT NULL,
    affiliate_link_id INTEGER NULL,
    capper_username VARCHAR(50) NULL,
    ticket_id VARCHAR(36) NULL,
    source VARCHAR(50) NULL,
    click_token VARCHAR(64) NOT NULL UNIQUE,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(affiliate_link_id) REFERENCES affiliate_links (id) ON DELETE SET NULL,
    FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE SET NULL
)
"""

STRIPE_EVENTS_DDL = """
CREATE TABLE stripe_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stripe_event_id VARCHAR(120) NOT NULL UNIQUE,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

ALIAS_OVERRIDES_DDL = """
CREATE TABLE alias_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_type VARCHAR(20) NOT NULL,
    alias VARCHAR(100) NOT NULL,
    canonical_value VARCHAR(120) NOT NULL,
    created_by VARCHAR(120) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if 'tickets' in table_names:
        existing = {col['name'] for col in inspector.get_columns('tickets')}
        statements: list[str] = []
        if 'source_type' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN source_type VARCHAR(30)')
        if 'source_ref' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN source_ref VARCHAR(255)')
        if 'source_payload_json' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN source_payload_json TEXT')
        if 'dedupe_key' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN dedupe_key VARCHAR(64)')
        if 'duplicate_of_ticket_id' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN duplicate_of_ticket_id VARCHAR(36)')
        if 'bookmaker' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN bookmaker VARCHAR(50)')
        if 'stake_amount' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN stake_amount FLOAT')
        if 'to_win_amount' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN to_win_amount FLOAT')
        if 'american_odds' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN american_odds INTEGER')
        if 'decimal_odds' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN decimal_odds FLOAT')
        if 'profit_amount' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN profit_amount FLOAT')
        if 'is_hidden' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0')
        if 'hidden_reason' not in existing:
            statements.append('ALTER TABLE tickets ADD COLUMN hidden_reason TEXT')
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    if 'ticket_legs' in table_names:
        existing = {col['name'] for col in inspector.get_columns('ticket_legs')}
        statements: list[str] = []
        if 'sport' not in existing:
            statements.append("ALTER TABLE ticket_legs ADD COLUMN sport VARCHAR(20) DEFAULT 'NBA'")
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

    if 'capper_profiles' in table_names:
        existing = {col['name'] for col in inspector.get_columns('capper_profiles')}
        statements: list[str] = []
        if 'claimed_by_user_id' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN claimed_by_user_id INTEGER')
        if 'display_name' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN display_name VARCHAR(80)')
        if 'bio' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN bio TEXT')
        if 'is_verified' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0')
        if 'verification_badge' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN verification_badge VARCHAR(30)')
        if 'verification_note' not in existing:
            statements.append('ALTER TABLE capper_profiles ADD COLUMN verification_note TEXT')
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

    with engine.begin() as conn:
        if 'review_queue' not in table_names:
            conn.execute(text("""
            CREATE TABLE review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id VARCHAR(36) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                priority VARCHAR(20) NOT NULL DEFAULT 'normal',
                reason_code VARCHAR(50) NOT NULL,
                summary TEXT NOT NULL,
                resolution_note TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
            )
            """))
        if 'watched_accounts' not in table_names:
            conn.execute(text(WATCHED_ACCOUNTS_DDL))
        if 'poll_runs' not in table_names:
            conn.execute(text(POLL_RUNS_DDL))
        if 'capper_profiles' not in table_names:
            conn.execute(text(CAPPER_PROFILES_DDL))
        if 'alias_overrides' not in table_names:
            conn.execute(text(ALIAS_OVERRIDES_DDL))
        if 'users' not in table_names:
            conn.execute(text(USERS_DDL))
        if 'user_sessions' not in table_names:
            conn.execute(text(USER_SESSIONS_DDL))
        if 'subscription_plans' not in table_names:
            conn.execute(text(SUBSCRIPTION_PLANS_DDL))
        if 'user_subscriptions' not in table_names:
            conn.execute(text(USER_SUBSCRIPTIONS_DDL))
        if 'affiliate_links' not in table_names:
            conn.execute(text(AFFILIATE_LINKS_DDL))
        if 'affiliate_clicks' not in table_names:
            conn.execute(text(AFFILIATE_CLICKS_DDL))
        if 'stripe_events' not in table_names:
            conn.execute(text(STRIPE_EVENTS_DDL))

    apply_migrations(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
