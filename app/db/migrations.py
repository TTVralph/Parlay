from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version='20260307_001_schema_migrations',
        description='create schema migrations tracking table',
        statements=(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """.strip(),
        ),
    ),
    Migration(
        version='20260307_002_user_roles',
        description='add user role and linked capper username columns',
        statements=(
            "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'",
            "ALTER TABLE users ADD COLUMN linked_capper_username VARCHAR(50)",
        ),
    ),
    Migration(
        version='20260307_003_capper_profile_fields',
        description='add capper profile presentation fields',
        statements=(
            "ALTER TABLE capper_profiles ADD COLUMN claimed_by_user_id INTEGER",
            "ALTER TABLE capper_profiles ADD COLUMN display_name VARCHAR(80)",
            "ALTER TABLE capper_profiles ADD COLUMN bio TEXT",
        ),
    ),
    Migration(
        version='20260307_004_capper_verification_fields',
        description='add capper verification fields',
        statements=(
            "ALTER TABLE capper_profiles ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE capper_profiles ADD COLUMN verification_badge VARCHAR(30)",
            "ALTER TABLE capper_profiles ADD COLUMN verification_note TEXT",
        ),
    ),
    Migration(
        version='20260307_005_subscription_provider_fields',
        description='add provider subscription/customer ids',
        statements=(
            'ALTER TABLE user_subscriptions ADD COLUMN provider_customer_id VARCHAR(120)',
            'ALTER TABLE user_subscriptions ADD COLUMN provider_subscription_id VARCHAR(120)',
        ),
    ),
    Migration(
        version='20260307_006_billing_email_affiliate_tracking',
        description='add billing invoices, email notifications, and affiliate conversions',
        statements=(
            '''
            CREATE TABLE IF NOT EXISTS billing_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id VARCHAR(120) NOT NULL UNIQUE,
                provider_invoice_id VARCHAR(120),
                user_id INTEGER,
                subscription_id INTEGER,
                status VARCHAR(30) NOT NULL DEFAULT 'open',
                amount_paid FLOAT NOT NULL DEFAULT 0,
                currency VARCHAR(10) NOT NULL DEFAULT 'usd',
                hosted_invoice_url TEXT,
                period_start DATETIME,
                period_end DATETIME,
                paid_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip(),
            '''
            CREATE TABLE IF NOT EXISTS email_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                subscription_id INTEGER,
                to_email VARCHAR(120) NOT NULL,
                template_key VARCHAR(50) NOT NULL,
                event_type VARCHAR(80) NOT NULL,
                subject VARCHAR(200) NOT NULL,
                body_json TEXT NOT NULL DEFAULT '{}',
                status VARCHAR(30) NOT NULL DEFAULT 'sent',
                sent_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip(),
            '''
            CREATE TABLE IF NOT EXISTS affiliate_conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                click_id INTEGER,
                click_token VARCHAR(64) NOT NULL,
                bookmaker VARCHAR(50) NOT NULL,
                revenue_amount FLOAT NOT NULL DEFAULT 0,
                currency VARCHAR(10) NOT NULL DEFAULT 'usd',
                external_ref VARCHAR(120) UNIQUE,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip(),
        ),
    ),
    Migration(
        version='20260307_007_invoice_pdf_email_provider_affiliate_webhooks',
        description='add invoice pdf metadata, email provider fields, and affiliate webhook events',
        statements=(
            'ALTER TABLE billing_invoices ADD COLUMN pdf_download_token VARCHAR(120)',
            'ALTER TABLE billing_invoices ADD COLUMN pdf_filename VARCHAR(180)',
            'ALTER TABLE billing_invoices ADD COLUMN pdf_generated_at DATETIME',
            'ALTER TABLE email_notifications ADD COLUMN provider VARCHAR(40)',
            'ALTER TABLE email_notifications ADD COLUMN provider_message_id VARCHAR(160)',
            '''
            CREATE TABLE IF NOT EXISTS affiliate_webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type VARCHAR(30) NOT NULL,
                network VARCHAR(50),
                external_ref VARCHAR(120),
                click_token VARCHAR(64),
                status VARCHAR(30) NOT NULL DEFAULT 'received',
                conversion_id INTEGER,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip(),
        ),
    ),
    Migration(
        version='20260310_008_public_slip_results',
        description='add persistent public slip results for shareable checks',
        statements=(
            '''
            CREATE TABLE IF NOT EXISTS public_slip_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id VARCHAR(16) NOT NULL UNIQUE,
                raw_slip_text TEXT NOT NULL,
                parsed_legs_json TEXT NOT NULL DEFAULT '[]',
                legs_json TEXT NOT NULL DEFAULT '[]',
                matched_events_json TEXT NOT NULL DEFAULT '[]',
                overall_result VARCHAR(20) NOT NULL,
                parser_confidence VARCHAR(20),
                bet_date DATETIME,
                stake_amount FLOAT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip(),
        ),
    )
)

def _table_exists(engine: Engine, table_name: str) -> bool:
    return table_name in set(inspect(engine).get_table_names())


def _column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    if not _table_exists(engine, table_name):
        return False
    return column_name in {col['name'] for col in inspect(engine).get_columns(table_name)}


def ensure_schema_migrations_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(MIGRATIONS[0].statements[0]))


def get_applied_versions(engine: Engine) -> set[str]:
    ensure_schema_migrations_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(text('SELECT version FROM schema_migrations')).fetchall()
    return {row[0] for row in rows}


def apply_migrations(engine: Engine) -> list[str]:
    ensure_schema_migrations_table(engine)
    applied = get_applied_versions(engine)
    newly_applied: list[str] = []
    for migration in MIGRATIONS[1:]:
        if migration.version in applied:
            continue
        statements = list(migration.statements)
        if migration.version == '20260307_002_user_roles':
            statements = []
            if _table_exists(engine, 'users') and not _column_exists(engine, 'users', 'role'):
                statements.append("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'")
            if _table_exists(engine, 'users') and not _column_exists(engine, 'users', 'linked_capper_username'):
                statements.append('ALTER TABLE users ADD COLUMN linked_capper_username VARCHAR(50)')
        elif migration.version == '20260307_003_capper_profile_fields':
            statements = []
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'claimed_by_user_id'):
                statements.append('ALTER TABLE capper_profiles ADD COLUMN claimed_by_user_id INTEGER')
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'display_name'):
                statements.append('ALTER TABLE capper_profiles ADD COLUMN display_name VARCHAR(80)')
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'bio'):
                statements.append('ALTER TABLE capper_profiles ADD COLUMN bio TEXT')

        elif migration.version == '20260307_004_capper_verification_fields':
            statements = []
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'is_verified'):
                statements.append("ALTER TABLE capper_profiles ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0")
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'verification_badge'):
                statements.append('ALTER TABLE capper_profiles ADD COLUMN verification_badge VARCHAR(30)')
            if _table_exists(engine, 'capper_profiles') and not _column_exists(engine, 'capper_profiles', 'verification_note'):
                statements.append('ALTER TABLE capper_profiles ADD COLUMN verification_note TEXT')

        elif migration.version == '20260307_005_subscription_provider_fields':
            statements = []
            if _table_exists(engine, 'user_subscriptions') and not _column_exists(engine, 'user_subscriptions', 'provider_customer_id'):
                statements.append('ALTER TABLE user_subscriptions ADD COLUMN provider_customer_id VARCHAR(120)')
            if _table_exists(engine, 'user_subscriptions') and not _column_exists(engine, 'user_subscriptions', 'provider_subscription_id'):
                statements.append('ALTER TABLE user_subscriptions ADD COLUMN provider_subscription_id VARCHAR(120)')

        elif migration.version == '20260307_006_billing_email_affiliate_tracking':
            statements = list(migration.statements)
        elif migration.version == '20260307_007_invoice_pdf_email_provider_affiliate_webhooks':
            statements = []
            if _table_exists(engine, 'billing_invoices') and not _column_exists(engine, 'billing_invoices', 'pdf_download_token'):
                statements.append('ALTER TABLE billing_invoices ADD COLUMN pdf_download_token VARCHAR(120)')
            if _table_exists(engine, 'billing_invoices') and not _column_exists(engine, 'billing_invoices', 'pdf_filename'):
                statements.append('ALTER TABLE billing_invoices ADD COLUMN pdf_filename VARCHAR(180)')
            if _table_exists(engine, 'billing_invoices') and not _column_exists(engine, 'billing_invoices', 'pdf_generated_at'):
                statements.append('ALTER TABLE billing_invoices ADD COLUMN pdf_generated_at DATETIME')
            if _table_exists(engine, 'email_notifications') and not _column_exists(engine, 'email_notifications', 'provider'):
                statements.append('ALTER TABLE email_notifications ADD COLUMN provider VARCHAR(40)')
            if _table_exists(engine, 'email_notifications') and not _column_exists(engine, 'email_notifications', 'provider_message_id'):
                statements.append('ALTER TABLE email_notifications ADD COLUMN provider_message_id VARCHAR(160)')
            if not _table_exists(engine, 'affiliate_webhook_events'):
                statements.append('''
            CREATE TABLE IF NOT EXISTS affiliate_webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type VARCHAR(30) NOT NULL,
                network VARCHAR(50),
                external_ref VARCHAR(120),
                click_token VARCHAR(64),
                status VARCHAR(30) NOT NULL DEFAULT 'received',
                conversion_id INTEGER,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            '''.strip())
        elif migration.version == '20260310_008_public_slip_results':
            statements = list(migration.statements)
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(
                text('INSERT INTO schema_migrations (version, description, applied_at) VALUES (:version, :description, :applied_at)'),
                {
                    'version': migration.version,
                    'description': migration.description,
                    'applied_at': datetime.utcnow(),
                },
            )
        newly_applied.append(migration.version)
    return newly_applied
