"""External Postgres / Neon adapter: read-only access to outside databases.

Security: connections are opened read-only (default_transaction_read_only=on)
and queries are limited + timed. Truss never writes to a user's external DB.
"""
import asyncio
import logging

import asyncpg

logger = logging.getLogger("truss.connectors.postgres")

QUERY_TIMEOUT_S = 15.0
MAX_ROWS = 200


def _dsn(config: dict) -> str:
    user = config.get("user", "")
    password = config.get("password", "")
    host = config.get("host", "")
    port = int(config.get("port", 5432))
    database = config.get("database", "")
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{database}"


async def _connect(config: dict) -> asyncpg.Connection:
    ssl = config.get("ssl")
    ssl_ctx = "require" if ssl in (True, "require", "true", "1") else None
    conn = await asyncio.wait_for(
        asyncpg.connect(
            _dsn(config),
            ssl=ssl_ctx,
            server_settings={"default_transaction_read_only": "on"},
        ),
        timeout=QUERY_TIMEOUT_S,
    )
    return conn


async def test_connection(config: dict) -> dict:
    """Open a connection, run SELECT 1, report server version."""
    try:
        conn = await _connect(config)
        try:
            version = await conn.fetchval("SELECT version()")
            return {"ok": True, "version": version}
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def introspect(config: dict) -> dict:
    """List tables + columns from information_schema (read-only)."""
    try:
        conn = await _connect(config)
        try:
            rows = await conn.fetch(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            tables: dict[str, list[dict]] = {}
            for r in rows:
                tables.setdefault(r["table_name"], []).append(
                    {"column": r["column_name"], "type": r["data_type"]}
                )
            return {"ok": True, "tables": tables}
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def run_query(config: dict, sql: str, limit: int = 50) -> dict:
    """Run a read-only SELECT. Rejects non-SELECT statements up front."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.lower().startswith("select"):
        return {"ok": False, "error": "only SELECT statements are allowed"}
    limit = min(max(1, limit), MAX_ROWS)

    try:
        conn = await _connect(config)
        try:
            rows = await asyncio.wait_for(
                conn.fetch(f"SELECT * FROM ({stripped}) AS _q LIMIT {limit}"),
                timeout=QUERY_TIMEOUT_S,
            )
            return {
                "ok": True,
                "row_count": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
                "rows": [dict(r) for r in rows],
            }
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
