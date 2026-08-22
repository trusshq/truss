"""Lightweight idempotent schema migration.

`Base.metadata.create_all` creates missing TABLES but never adds missing
COLUMNS to existing ones. This module adds columns introduced after the
initial schema, using `ADD COLUMN IF NOT EXISTS` so it is safe to run on
every boot. Alembic takes over for real versioned migrations later.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger("truss.migrate")

# (table, column, sql type, default) — additive only, never destructive
COLUMN_MIGRATIONS: list[tuple[str, str, str, str]] = [
    # tenant workspace profile / namespace fields
    ("tenants", "description", "TEXT", "''"),
    ("tenants", "website", "VARCHAR(500)", "''"),
    ("tenants", "industry", "VARCHAR(100)", "''"),
    ("tenants", "company_size", "VARCHAR(50)", "''"),
    ("tenants", "logo_url", "VARCHAR(500)", "''"),
    ("tenants", "timezone", "VARCHAR(64)", "'UTC'"),
    ("tenants", "locale", "VARCHAR(16)", "'en-US'"),
    ("tenants", "settings", "JSONB", "'{}'::jsonb"),
    # user profile fields
    ("users", "title", "VARCHAR(200)", "''"),
    ("users", "phone", "VARCHAR(50)", "''"),
    ("users", "avatar_url", "VARCHAR(500)", "''"),
    ("users", "timezone", "VARCHAR(64)", "'UTC'"),
    ("users", "locale", "VARCHAR(16)", "'en-US'"),
    ("users", "last_login_at", "TIMESTAMPTZ", "NULL"),
]


async def run_migrations(conn: AsyncConnection) -> None:
    applied = 0
    for table, column, col_type, default in COLUMN_MIGRATIONS:
        await conn.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type} NOT NULL DEFAULT {default}")
            if default != "NULL"
            else text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}")
        )
        applied += 1
    logger.info("Schema migration pass complete (%d column checks)", applied)
