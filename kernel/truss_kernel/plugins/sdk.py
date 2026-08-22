"""Truss Plugin SDK — manifest validation + scaffolding.

The SDK is the developer-facing contract for building Truss plugins. It gives:
1. `validate_manifest(raw)` — strict validation with actionable error messages
   (beyond what pydantic's model_validate gives), checking cross-references,
   slug formats, reserved ids, and permission validity.
2. `scaffold(plugin_id, ...)` — generates a ready-to-edit plugin directory.

Used by:
- the kernel at discovery time (warn on invalid manifests)
- the `truss-plugin` CLI (`python -m truss_kernel.plugins.sdk new my-plugin`)
- the publish endpoint (reject invalid manifests before they hit the catalog)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from truss_kernel.plugins.manifest import PluginManifest

SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# ids a plugin may never claim (kernel internals / first-party apps)
RESERVED_IDS = {"kernel", "truss", "core", "system", "admin"}

# permissions a plugin may request (surfaced to admins on install)
VALID_PERMISSIONS = {
    "objects:write",
    "records:write",
    "records:read",
    "events:emit",
    "ai:tools",
    "connectors:use",
}

VALID_FIELD_TYPES = {
    "text", "textarea", "number", "currency", "email", "phone", "url",
    "date", "datetime", "select", "multiselect", "checkbox", "relation",
}

VALID_TOOL_ACTIONS = {
    "create_record", "update_record", "query_records",
    "send_webhook", "analytics",
}

VALID_UI_VIEWS = {"table", "kanban", "detail", "dashboard"}


class ManifestError(Exception):
    """A manifest failed validation. `errors` is a list of human-readable strings."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_manifest(raw: dict) -> PluginManifest:
    """Strict-validate a raw manifest dict. Raises ManifestError with all issues."""
    errors: list[str] = []

    # --- structural (pydantic) ---
    try:
        manifest = PluginManifest.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        raise ManifestError([f"manifest structure invalid: {e}"]) from e

    # --- id ---
    if manifest.id.lower() in RESERVED_IDS:
        errors.append(f"id '{manifest.id}' is reserved")
    if not SLUG_RE.match(manifest.id):
        errors.append(f"id '{manifest.id}' must match {SLUG_RE.pattern} (lowercase, digits, underscores)")

    # --- version ---
    if not VERSION_RE.match(manifest.version):
        errors.append(f"version '{manifest.version}' must be semver MAJOR.MINOR.PATCH")

    # --- permissions ---
    for p in manifest.permissions:
        if p not in VALID_PERMISSIONS:
            errors.append(f"unknown permission '{p}' (valid: {', '.join(sorted(VALID_PERMISSIONS))})")

    # --- objects ---
    obj_slugs = set()
    for obj in manifest.objects:
        if not SLUG_RE.match(obj.slug):
            errors.append(f"object '{obj.slug}': slug must match {SLUG_RE.pattern}")
        if obj.slug in obj_slugs:
            errors.append(f"object slug '{obj.slug}' declared twice")
        obj_slugs.add(obj.slug)
        field_slugs = set()
        for f in obj.fields:
            if not SLUG_RE.match(f.slug):
                errors.append(f"object '{obj.slug}' field '{f.slug}': bad slug")
            if f.slug in field_slugs:
                errors.append(f"object '{obj.slug}': field '{f.slug}' declared twice")
            field_slugs.add(f.slug)
            if f.type not in VALID_FIELD_TYPES:
                errors.append(f"object '{obj.slug}' field '{f.slug}': unknown type '{f.type}'")
            if f.type == "select" and not (f.options or {}).get("choices"):
                errors.append(f"object '{obj.slug}' field '{f.slug}': select needs options.choices")
            if f.type == "relation":
                rel = (f.options or {}).get("related_object")
                if not rel:
                    errors.append(f"object '{obj.slug}' field '{f.slug}': relation needs options.related_object")

    # --- tools ---
    tool_slugs = set()
    for t in manifest.tools:
        if not SLUG_RE.match(t.slug):
            errors.append(f"tool '{t.slug}': bad slug")
        if t.slug in tool_slugs:
            errors.append(f"tool slug '{t.slug}' declared twice")
        tool_slugs.add(t.slug)
        if t.action not in VALID_TOOL_ACTIONS:
            errors.append(f"tool '{t.slug}': unknown action '{t.action}' (valid: {', '.join(sorted(VALID_TOOL_ACTIONS))})")
        if t.action in ("create_record", "update_record", "query_records") and not t.object:
            errors.append(f"tool '{t.slug}': record actions require an 'object' slug")
        if t.object and t.object not in obj_slugs:
            errors.append(f"tool '{t.slug}': object '{t.object}' not declared in this plugin")

    # --- automations ---
    auto_slugs = set()
    for a in manifest.automations:
        if not SLUG_RE.match(a.slug):
            errors.append(f"automation '{a.slug}': bad slug")
        if a.slug in auto_slugs:
            errors.append(f"automation slug '{a.slug}' declared twice")
        auto_slugs.add(a.slug)
        if a.object and a.object not in obj_slugs:
            errors.append(f"automation '{a.slug}': object '{a.object}' not declared in this plugin")
        if not a.actions:
            errors.append(f"automation '{a.slug}': needs at least one action")

    # --- ui ---
    ui_slugs = set()
    for u in manifest.ui:
        if not SLUG_RE.match(u.slug):
            errors.append(f"ui '{u.slug}': bad slug")
        if u.slug in ui_slugs:
            errors.append(f"ui slug '{u.slug}' declared twice")
        ui_slugs.add(u.slug)
        if u.view not in VALID_UI_VIEWS:
            errors.append(f"ui '{u.slug}': unknown view '{u.view}' (valid: {', '.join(sorted(VALID_UI_VIEWS))})")
        if u.view in ("table", "kanban", "detail") and u.object and u.object not in obj_slugs:
            errors.append(f"ui '{u.slug}': object '{u.object}' not declared in this plugin")

    if errors:
        raise ManifestError(errors)
    return manifest


# ---------------- scaffolding ----------------

SCAFFOLD_MANIFEST = {
    "id": "{plugin_id}",
    "name": "{name}",
    "version": "0.1.0",
    "description": "{description}",
    "author": "{author}",
    "icon": "🧩",
    "permissions": ["objects:write", "records:write", "events:emit"],
    "objects": [
        {
            "slug": "{plugin_id}_item",
            "name": "{name} Item",
            "name_plural": "{name} Items",
            "description": "Example object — edit me",
            "icon": "🧩",
            "fields": [
                {"slug": "name", "name": "Name", "type": "text", "required": True, "position": 0},
                {"slug": "status", "name": "Status", "type": "select", "position": 1,
                 "options": {"choices": ["New", "In Progress", "Done"]}},
            ],
        }
    ],
    "tools": [
        {
            "slug": "create_item",
            "name": "Create Item",
            "description": "Create a new {name} item",
            "action": "create_record",
            "object": "{plugin_id}_item",
            "params": [
                {"name": "name", "type": "string", "description": "Item name", "required": True},
            ],
        }
    ],
    "automations": [],
    "ui": [
        {"slug": "{plugin_id}-table", "label": "{name}", "icon": "🧩", "view": "table", "object": "{plugin_id}_item"}
    ],
}

SCAFFOLD_README = """# {name}

A Truss plugin.

## Develop

1. Edit `plugin.json` — declare objects, fields, AI tools, automations, and UI surfaces.
2. Validate: `python -m truss_kernel.plugins.sdk validate {plugin_id}`
3. Drop this folder into the kernel's external plugins dir (or publish it).

## Publish

```
POST /api/marketplace/publish
{{ "manifest": <plugin.json contents> }}
```

See the Truss developer docs for the full manifest reference.
"""


def scaffold(plugin_id: str, name: str | None = None, description: str = "",
             author: str = "", dest: Path | None = None) -> Path:
    """Generate a plugin directory with plugin.json + README.md. Returns the dir."""
    if not SLUG_RE.match(plugin_id):
        raise ManifestError([f"plugin_id '{plugin_id}' must match {SLUG_RE.pattern}"])
    name = name or plugin_id.replace("_", " ").replace("-", " ").title()
    dest = dest or Path(plugin_id)
    dest.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(json.dumps(SCAFFOLD_MANIFEST)
                          .replace("{plugin_id}", plugin_id)
                          .replace("{name}", name)
                          .replace("{description}", description or f"{name} plugin for Truss")
                          .replace("{author}", author))
    # validate our own scaffold so the template can never drift out of spec
    validate_manifest(manifest)

    (dest / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (dest / "README.md").write_text(
        SCAFFOLD_README.replace("{name}", name).replace("{plugin_id}", plugin_id),
        encoding="utf-8",
    )
    return dest


# ---------------- CLI ----------------

def _main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "new":
        plugin_id = argv[2]
        name = argv[3] if len(argv) > 3 else None
        try:
            d = scaffold(plugin_id, name=name)
            print(f"created {d}/plugin.json + README.md — edit and validate away!")
            return 0
        except ManifestError as e:
            print("scaffold failed:")
            for err in e.errors:
                print("  - " + err)
            return 1
    if len(argv) >= 3 and argv[1] == "validate":
        path = Path(argv[2])
        if path.is_dir():
            path = path / "plugin.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            m = validate_manifest(raw)
            print(f"OK: {m.id} v{m.version} — {len(m.objects)} object(s), {len(m.tools)} tool(s)")
            return 0
        except ManifestError as e:
            print("invalid manifest:")
            for err in e.errors:
                print("  - " + err)
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"could not read manifest: {e}")
            return 1
    print("usage: python -m truss_kernel.plugins.sdk new <plugin_id> [name]")
    print("       python -m truss_kernel.plugins.sdk validate <plugin.json|dir>")
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv))
