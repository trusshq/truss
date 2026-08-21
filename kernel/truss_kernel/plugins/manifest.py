"""Plugin manifest schema — the 'harness' contract.

A plugin is a declarative bundle: metadata objects, AI tools, automations,
UI surfaces, and requested permissions. No user code executes in v1 —
everything is config interpreted by the kernel runtime.
"""
from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    slug: str
    name: str
    type: str = "text"
    required: bool = False
    position: int = 0
    options: dict = Field(default_factory=dict)


class ObjectSpec(BaseModel):
    slug: str
    name: str
    name_plural: str = ""
    description: str = ""
    icon: str = "📦"
    fields: list[FieldSpec] = Field(default_factory=list)


class ToolParam(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False


class ToolSpec(BaseModel):
    """An AI-callable capability. Maps to a kernel action the agent may invoke."""

    slug: str
    name: str
    description: str
    # which kernel action backs this tool: create_record | update_record |
    # query_records | send_webhook | ...
    action: str
    params: list[ToolParam] = Field(default_factory=list)
    # object slug this tool operates on (for record actions)
    object: str | None = None


class AutomationSpec(BaseModel):
    """Declarative trigger -> actions rule, interpreted by the kernel."""

    slug: str
    name: str
    trigger: str  # e.g. record.created, record.updated
    object: str | None = None  # scope to an object slug, or null = all
    condition: dict = Field(default_factory=dict)  # simple field-eq conditions
    actions: list[dict] = Field(default_factory=list)  # [{action: ..., ...}]


class UISurface(BaseModel):
    slug: str
    label: str
    icon: str = "🧩"
    # v1: kernel-rendered views over objects
    view: str = "table"  # table | kanban | detail | dashboard
    object: str | None = None
    config: dict = Field(default_factory=dict)


class PluginManifest(BaseModel):
    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    icon: str = "🧩"
    # permissions the plugin requests (surfaced to the tenant admin on install)
    permissions: list[str] = Field(default_factory=list)
    objects: list[ObjectSpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    automations: list[AutomationSpec] = Field(default_factory=list)
    ui: list[UISurface] = Field(default_factory=list)
