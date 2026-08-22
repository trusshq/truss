"""Developer platform routes: OpenAPI spec + curated API reference.

FastAPI already serves interactive docs at /docs and the raw spec at
/openapi.json. These endpoints package the same information for developers
building against Truss: a stable spec URL under /api and a human-readable
markdown reference grouped by capability.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from truss_kernel.deps import AuthContext, require_viewer

router = APIRouter(prefix="/api/dev", tags=["developer"])


@router.get("/openapi.json")
async def openapi_spec(request: Request, auth: AuthContext = Depends(require_viewer)):
    """The full OpenAPI 3 spec for the kernel API (stable URL for codegen)."""
    return request.app.openapi()


REFERENCE_MD = """# Truss Kernel API Reference

Base URL: `http://<host>:8000` · Auth: `Authorization: Bearer <token>`
Interactive docs: `/docs` · Raw spec: `/api/dev/openapi.json`

## Authentication
| Method | Path | Description |
|---|---|---|
| POST | /api/auth/signup | Create workspace + owner account |
| POST | /api/auth/login | Get an access token |
| GET  | /api/auth/me | Current user + tenant |

## Objects & Records (the data layer)
| Method | Path | Description |
|---|---|---|
| GET | /api/objects | List metadata objects |
| POST | /api/objects | Create a custom object (admin) |
| GET | /api/records/{object} | List/search records (paginated) |
| POST | /api/records/{object} | Create a record (validated) |
| GET | /api/records/{object}/{id} | Get one record |
| PATCH | /api/records/{object}/{id} | Update a record |
| DELETE | /api/records/{object}/{id} | Soft-delete (to trash) |
| GET | /api/records/trash | List trashed records |
| POST | /api/records/trash/{id}/restore | Restore from trash |
| GET | /api/records/{object}/{id}/history | Version history |
| GET | /api/records/{object}/export.csv | Export CSV |
| POST | /api/records/{object}/import.csv | Import CSV |

## AI (BYOK)
| Method | Path | Description |
|---|---|---|
| POST | /api/ai/keys | Add an AI provider key (encrypted at rest) |
| GET | /api/ai/keys | List keys (never returns secrets) |
| POST | /api/ai/chat | Chat through the agent loop (tools enabled) |

## AI Employees (agents)
| Method | Path | Description |
|---|---|---|
| POST | /api/agents | Hire an AI employee |
| GET | /api/agents | List agents |
| POST | /api/agents/{id}/tasks | Assign a task |
| POST | /api/agents/{id}/tasks/{tid}/run | Run a task now |
| POST | /api/agents/{id}/tasks/{tid}/approve | Approve a gated task |
| POST | /api/agents/{id}/delegate | Delegate to a report |

## Org, Goals & Review
| Method | Path | Description |
|---|---|---|
| GET | /api/org/tree | Reporting hierarchy |
| POST | /api/org/goals | Create a goal |
| GET | /api/org/review | Pending approvals inbox |
| GET | /api/org/budget | Token budget ledger |

## Orchestration (autopilot)
| Method | Path | Description |
|---|---|---|
| POST | /api/orchestration/schedules | Schedule recurring agent work |
| POST | /api/orchestration/triggers | React to record events |
| POST | /api/orchestration/pipelines | Chain agents into a pipeline |
| POST | /api/orchestration/pipelines/{id}/run | Run a pipeline |

## Insights
| Method | Path | Description |
|---|---|---|
| POST | /api/insights/query | Analytics (count/group_by/sum/avg/time_series) |
| GET | /api/insights/agents | Agent performance scorecards |
| GET | /api/insights/timeline | Unified activity feed |

## Plugins & Marketplace
| Method | Path | Description |
|---|---|---|
| GET | /api/plugins | Installed plugins |
| POST | /api/plugins/install | Install a builtin plugin |
| GET | /api/marketplace/plugins | Community catalog |
| POST | /api/marketplace/publish | Publish a plugin (SDK-validated) |
| POST | /api/marketplace/validate | Dry-run manifest validation |

## Programmatic access
| Method | Path | Description |
|---|---|---|
| POST | /api/keys | Create an API key (scopes: records/objects/agents) |
| GET | /api/keys | List keys (prefix only) |

API keys use the same `Authorization: Bearer` header and act as their owner,
capped by their scopes.
"""


@router.get("/reference", response_class=PlainTextResponse)
async def api_reference(auth: AuthContext = Depends(require_viewer)):
    """Curated markdown reference of the kernel API, grouped by capability."""
    return REFERENCE_MD
