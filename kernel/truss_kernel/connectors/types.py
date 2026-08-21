"""Connector type registry: required config fields + implementation status."""

CONNECTOR_TYPES: dict[str, dict] = {
    "webhook": {
        "label": "Webhook (event forwarding)",
        "required": ["url"],
        "optional": ["secret", "events"],
        "implemented": True,
        "help": "Forwards kernel events to your URL as signed JSON POSTs. "
                "Point it at PostHog, a warehouse ingest, Zapier, or your own service. "
                "'events' is an optional list of type prefixes to match (e.g. ['record.']); "
                "empty = forward everything.",
    },
    "postgres": {
        "label": "External Postgres / Neon",
        "required": ["host", "database", "user"],
        "optional": ["port", "password", "ssl"],
        "implemented": True,
        "help": "Read-only access to an outside Postgres. Test the connection, "
                "introspect tables, and run SELECT queries from Truss.",
    },
    "s3": {
        "label": "S3-compatible storage (R2, MinIO, AWS)",
        "required": ["endpoint", "bucket", "access_key_id", "secret_access_key"],
        "optional": ["region"],
        "implemented": False,
        "help": "Object storage adapter ships in a later phase.",
    },
    "smtp": {
        "label": "SMTP (outbound email)",
        "required": ["host", "port", "from_email"],
        "optional": ["user", "password", "starttls"],
        "implemented": False,
        "help": "Email adapter ships in a later phase.",
    },
}

SECRET_FIELDS = {"password", "secret", "secret_access_key", "access_key_id", "api_key"}


def validate_config(conn_type: str, config: dict) -> str | None:
    """Return an error string, or None if the config is valid."""
    spec = CONNECTOR_TYPES.get(conn_type)
    if spec is None:
        return f"unknown connector type '{conn_type}'"
    missing = [f for f in spec["required"] if not config.get(f)]
    if missing:
        return f"missing required config fields: {', '.join(missing)}"
    if conn_type == "webhook":
        url = str(config.get("url", ""))
        if not url.startswith(("http://", "https://")):
            return "webhook url must start with http:// or https://"
        events = config.get("events")
        if events is not None and not isinstance(events, list):
            return "'events' must be a list of type prefixes"
    if conn_type == "postgres":
        try:
            int(config.get("port", 5432))
        except (TypeError, ValueError):
            return "port must be a number"
    return None


def mask_config(config: dict) -> dict:
    """Safe-to-display copy: secrets masked."""
    out = {}
    for k, v in config.items():
        if k in SECRET_FIELDS and v:
            s = str(v)
            out[k] = (s[:2] + "…" + s[-2:]) if len(s) > 6 else "…"
        else:
            out[k] = v
    return out
