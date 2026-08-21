"""Webhook connector adapter: forward kernel events to external URLs.

Design (outbox pattern):
1. On every bus event, find the tenant's ENABLED webhook connectors whose
   `events` filter matches.
2. Insert a WebhookDelivery outbox row in the SAME transaction as the event
   (atomic: no delivery without a persisted event, and vice versa).
3. Register a session after_commit hook; once the transaction commits, deliver
   each pending row via HTTP POST with an HMAC-SHA256 signature header.
4. Update the row to success/failed (with http status / error).

This is the BYO-analytics seam: point a webhook at PostHog, a warehouse, or any
ingest endpoint and Truss streams its events there — no analytics baked in.
"""
import hashlib
import hmac
import json
import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai.vault import decrypt_secret
from truss_kernel.models.connector import Connector, WebhookDelivery

logger = logging.getLogger("truss.connectors.webhook")

DELIVERY_TIMEOUT_S = 10.0


def _matches(events_filter: list | None, event_type: str) -> bool:
    if not events_filter:
        return True
    return any(event_type == p or event_type.startswith(p) for p in events_filter)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def on_event(envelope: dict) -> None:
    """Bus wildcard handler: enqueue outbox rows for matching webhook connectors."""
    db: AsyncSession | None = envelope.get("_db")
    if db is None:
        return
    try:
        tenant_id = uuid.UUID(envelope["tenant_id"])
    except (KeyError, ValueError):
        return

    connectors = (await db.execute(
        select(Connector).where(
            Connector.tenant_id == tenant_id,
            Connector.type == "webhook",
            Connector.enabled.is_(True),
        )
    )).scalars().all()
    if not connectors:
        return

    event_type = envelope.get("type", "")
    payload = {
        "event_id": envelope.get("id"),
        "type": event_type,
        "tenant_id": str(tenant_id),
        "plugin_id": envelope.get("plugin_id", ""),
        "payload": envelope.get("payload", {}),
    }

    # Capture PLAIN DATA for post-commit delivery — never ORM objects, which
    # would be detached after the session closes.
    items: list[dict] = []
    for c in connectors:
        try:
            config = json.loads(decrypt_secret(c.config_enc)) if c.config_enc else {}
        except (ValueError, json.JSONDecodeError):
            continue
        if not _matches(config.get("events"), event_type):
            continue
        row = WebhookDelivery(
            id=uuid.uuid4(),  # assign now — the column default only fires at INSERT,
            # and we need the id before flush to reference it post-commit
            tenant_id=tenant_id,
            connector_id=c.id,
            event_id=uuid.UUID(envelope["id"]) if envelope.get("id") else uuid.uuid4(),
            event_type=event_type,
            status="pending",
        )
        db.add(row)
        items.append({
            "delivery_id": str(row.id),
            "url": config.get("url", ""),
            "secret": config.get("secret", ""),
            "payload": payload,
        })

    if items:
        await db.flush()
        # deliver after the transaction commits (never inside it)
        _schedule_after_commit(db, items)


def _schedule_after_commit(db: AsyncSession, items: list[dict]) -> None:
    """Attach a one-shot after_commit hook that delivers the queued rows.

    AsyncSession doesn't support ORM events directly; we listen on the
    underlying sync_session. The commit runs on the same event-loop thread
    (via greenlet), so we can schedule an async delivery task from the hook.
    """
    from sqlalchemy import event as sa_event

    def _deliver(_session):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_deliver_all(items))
        except RuntimeError:
            asyncio.run(_deliver_all(items))

    sa_event.listen(db.sync_session, "after_commit", _deliver, once=True)


async def _deliver_all(items: list[dict]) -> None:
    from truss_kernel.db import SessionLocal
    async with SessionLocal() as session:
        for item in items:
            await deliver_item(session, item)
        await session.commit()


async def deliver_item(session: AsyncSession, item: dict) -> WebhookDelivery | None:
    """Deliver one outbox item (plain dict) and record the outcome."""
    row = await session.get(WebhookDelivery, uuid.UUID(item["delivery_id"]))
    if row is None:
        return None
    url = item.get("url", "")
    secret = item.get("secret", "")
    body = json.dumps(item.get("payload", {}), default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Truss-Webhook/1.0"}
    if secret:
        headers["X-Truss-Signature"] = _sign(secret, body)

    row.attempts += 1
    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_S) as client:
            resp = await client.post(url, content=body, headers=headers)
        row.last_http_status = resp.status_code
        if 200 <= resp.status_code < 300:
            row.status = "success"
            row.last_error = ""
        else:
            row.status = "failed"
            row.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        row.status = "failed"
        row.last_error = f"transport error: {e}"
    await session.flush()
    logger.info("webhook delivery %s -> %s (%s)", item["delivery_id"], url, row.status)
    return row
