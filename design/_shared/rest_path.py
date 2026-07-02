#!/usr/bin/env python3
"""
Shared REST path/verb derivation for design/ generative skills and
implementation/api-docs (stdlib only).

Extracted once a second real consumer (implementation/api-docs) needed the
exact same operation-IR -> REST path/verb derivation that rfc-to-api's
render_api.py already had — the docs renderer needs to show the same
method+path a rendered OpenAPI spec would have, not a near-identical
reimplementation that could quietly drift from it over time.
"""

from naming import slugify_table_name

KIND_TO_VERB = {
    "create": "POST",
    "read": "GET",
    "list": "GET",
    "update": "PATCH",
    "delete": "DELETE",
}


def derive_rest_path_verb(op: dict):
    """Returns (path, verb, high_confidence) for an rfc-to-api operation IR
    entry. high_confidence is False for the flat-fallback and action-kind
    cases, where the derivation is a best guess rather than a firm
    convention."""
    override = op.get("rest_override")
    if override:
        return override["path"], override["verb"], True  # explicit override

    kind = op["kind"]
    entity = op.get("entity")
    if entity is None:
        output = op.get("output", {})
        shape = output.get("shape", {})
        entity = shape.get("ref_entity") if shape.get("type") == "ref" else None
    if entity is None:
        for f in op.get("input", {}).get("fields", []):
            if f.get("type") == "ref":
                entity = f["ref_entity"]
                break

    if entity is None:
        flat = op["name"]
        return f"/{flat}", KIND_TO_VERB.get(kind, "POST"), False

    plural = slugify_table_name(entity)
    if kind == "create":
        return f"/{plural}", "POST", True
    if kind == "list":
        return f"/{plural}", "GET", True
    if kind in ("read", "update", "delete"):
        return f"/{plural}/{{id}}", KIND_TO_VERB[kind], True

    action_part = op["name"]
    for prefix in ("approve", "reject", "cancel", "publish", "archive", "activate", "deactivate"):
        if action_part.lower().startswith(prefix):
            action_part = prefix
            break
    return f"/{plural}/{{id}}/{action_part.lower()}", "POST", False
