"""Phase D analytics service: read-only aggregate queries over the record store.

Records live in `records.data` (JSONB). We aggregate with Postgres JSONB
operators so this stays fast at scale and never loads every row into Python.

Everything here is READ-ONLY and tenant-scoped. It is shared by:
- the /api/insights REST routes (dashboards)
- the kernel analytics tool offered to AI agents (natural-language data Q&A)

Supported queries (all respect soft-delete + tenancy):
- count: total records of an object
- group_by: count per distinct value of a field (select/text)
- sum / avg / min / max: numeric aggregate of a field, optionally grouped
- time_series: record count bucketed by day/week/month over created_at
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from truss_kernel.models.metadata import ObjectDef, Record
from truss_kernel.services import records as svc

logger = logging.getLogger("truss.analytics")

# cap group-by buckets so a high-cardinality field can't blow up a response
MAX_BUCKETS = 100

# Postgres regex for a numeric-looking JSONB text value
NUMERIC_RE = "^-?[0-9]+(\\.[0-9]+)?$"


class AnalyticsError(ValueError):
    pass


async def _get_object(db: AsyncSession, tenant_id: uuid.UUID, slug: str) -> ObjectDef:
    try:
        return await svc.get_object(db, tenant_id, slug)
    except svc.ObjectNotFound as e:
        raise AnalyticsError(str(e))


def _base_where(tenant_id: uuid.UUID, obj: ObjectDef):
    """The tenant + object + not-deleted predicate shared by every query."""
    return and_(
        Record.tenant_id == tenant_id,
        Record.object_id == obj.id,
        Record.deleted_at.is_(None),
    )


def _text(field: str):
    """JSONB text extraction: records.data->>'field'."""
    return Record.data[field].astext


def _num(field: str):
    """Cast a JSONB text value to float for numeric aggregation."""
    return cast(_text(field), Float)


def _is_numeric(field: str):
    """Only rows whose field value looks numeric (guards the float cast)."""
    return _text(field).op("~")(NUMERIC_RE)


async def count_records(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef) -> int:
    stmt = select(func.count(Record.id)).where(_base_where(tenant_id, obj))
    return int(await db.scalar(stmt) or 0)


async def group_by(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef,
                   field: str, metric: str = "count", value_field: str | None = None,
                   limit: int = MAX_BUCKETS) -> list[dict]:
    """Count (or sum/avg a numeric value_field) per distinct value of `field`."""
    key = _text(field)
    conds = [_base_where(tenant_id, obj), key.isnot(None)]

    if metric == "count":
        agg = func.count(Record.id)
    elif metric in ("sum", "avg"):
        if not value_field:
            raise AnalyticsError(f"metric '{metric}' requires value_field")
        conds.append(_is_numeric(value_field))
        agg = func.sum(_num(value_field)) if metric == "sum" else func.avg(_num(value_field))
    else:
        raise AnalyticsError(f"unsupported group metric '{metric}'")

    stmt = (
        select(key.label("key"), agg.label("value"))
        .where(and_(*conds))
        .group_by(key)
        .order_by(agg.desc())
        .limit(min(limit, MAX_BUCKETS))
    )
    rows = (await db.execute(stmt)).all()
    return [{"key": r.key, "value": float(r.value) if r.value is not None else 0.0} for r in rows]


async def numeric_summary(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef,
                          field: str) -> dict:
    """sum / avg / min / max / count for one numeric field."""
    stmt = select(
        func.count(Record.id),
        func.sum(_num(field)),
        func.avg(_num(field)),
        func.min(_num(field)),
        func.max(_num(field)),
    ).where(_base_where(tenant_id, obj), _is_numeric(field))
    row = (await db.execute(stmt)).one()
    cnt, total, avg, mn, mx = row
    return {
        "field": field,
        "count": int(cnt or 0),
        "sum": float(total) if total is not None else 0.0,
        "avg": float(avg) if avg is not None else 0.0,
        "min": float(mn) if mn is not None else 0.0,
        "max": float(mx) if mx is not None else 0.0,
    }


async def time_series(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef,
                      bucket: str = "day", days: int = 30) -> list[dict]:
    """Record count per time bucket over created_at, oldest -> newest."""
    bucket = bucket if bucket in ("day", "week", "month") else "day"
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    trunc = func.date_trunc(bucket, Record.created_at)
    stmt = (
        select(trunc.label("bucket"), func.count(Record.id).label("count"))
        .where(_base_where(tenant_id, obj), Record.created_at >= since)
        .group_by(trunc)
        .order_by(trunc)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"bucket": r.bucket.isoformat() if r.bucket else None, "count": int(r.count)}
        for r in rows
    ]


async def run_query(db: AsyncSession, tenant_id: uuid.UUID, query: dict) -> dict:
    """Dispatch a structured analytics query. Used by both the REST route and
    the agent analytics tool. Returns a JSON-serializable dict.

    query = {
      object: str (required)
      metric: 'count' | 'group_by' | 'sum' | 'avg' | 'min' | 'max' | 'summary' | 'time_series'
      field: str (for group_by / numeric / summary)
      value_field: str (for group_by sum/avg)
      bucket: 'day' | 'week' | 'month' (time_series)
      days: int (time_series window)
      limit: int (group_by buckets)
    }
    """
    object_slug = query.get("object")
    if not object_slug:
        raise AnalyticsError("'object' is required")
    obj = await _get_object(db, tenant_id, str(object_slug))
    metric = query.get("metric", "count")

    if metric == "count":
        return {"object": obj.slug, "metric": "count", "value": await count_records(db, tenant_id, obj)}

    if metric == "group_by":
        field = query.get("field")
        if not field:
            raise AnalyticsError("group_by requires 'field'")
        gm = "count" if not query.get("value_field") else "sum"
        rows = await group_by(
            db, tenant_id, obj, str(field),
            metric=gm,
            value_field=query.get("value_field"),
            limit=int(query.get("limit", MAX_BUCKETS)),
        )
        return {"object": obj.slug, "metric": "group_by", "field": field, "rows": rows}

    if metric in ("sum", "avg", "min", "max"):
        field = query.get("field")
        if not field:
            raise AnalyticsError(f"{metric} requires 'field'")
        s = await numeric_summary(db, tenant_id, obj, str(field))
        return {"object": obj.slug, "metric": metric, "field": field, "value": s[metric], "summary": s}

    if metric == "summary":
        field = query.get("field")
        if not field:
            raise AnalyticsError("summary requires 'field'")
        return {"object": obj.slug, "metric": "summary", **(await numeric_summary(db, tenant_id, obj, str(field)))}

    if metric == "time_series":
        rows = await time_series(
            db, tenant_id, obj,
            bucket=str(query.get("bucket", "day")),
            days=int(query.get("days", 30)),
        )
        return {"object": obj.slug, "metric": "time_series", "rows": rows}

    raise AnalyticsError(f"unsupported metric '{metric}'")
