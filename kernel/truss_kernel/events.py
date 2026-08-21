"""In-process event bus + persistence to event_log.

Every kernel action emits an event here. Subscribers (automation, analytics
forwarding, AI context) register callbacks. Kept deliberately simple:
async in-process dispatch + durable row in Postgres. Graduate to NATS later.
"""
import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.models.plugin import EventLog

logger = logging.getLogger("truss.events")

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._wildcard: list[Handler] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Subscribe to an exact type ('record.created') or '*' for all."""
        if event_type == "*":
            self._wildcard.append(handler)
        else:
            self._handlers[event_type].append(handler)

    async def emit(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        plugin_id: str = "",
        depth: int = 0,
    ) -> EventLog:
        """Persist the event, then fan out to handlers (errors never break the caller).

        `depth` tracks automation-caused recursion (envelope-only, never persisted)
        so the automation engine can cut off self-retriggering loops. Handlers also
        receive `_db` so they can act inside the same transaction as the emitter.
        """
        row = EventLog(
            tenant_id=tenant_id,
            type=event_type,
            actor_id=actor_id,
            plugin_id=plugin_id,
            payload=payload,
        )
        db.add(row)
        await db.flush()

        envelope = {
            "id": str(row.id),
            "type": event_type,
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id) if actor_id else None,
            "plugin_id": plugin_id,
            "payload": payload,
            "_db": db,
            "_depth": depth,
        }
        targets = list(self._handlers.get(event_type, [])) + list(self._wildcard)
        for handler in targets:
            try:
                await handler(envelope)
            except Exception:  # noqa: BLE001 - handlers must never break the emitter
                logger.exception("event handler failed for %s", event_type)
        return row


# Singleton bus for the whole kernel
bus = EventBus()
