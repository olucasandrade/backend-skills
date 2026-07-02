#!/usr/bin/env python3
"""
Deterministic IR -> Markdown docs skeleton renderer for api-docs
(stdlib only).

This script does NOT write endpoint descriptions or synthesize example
values — that's LLM work (see SKILL.md Step 3-4). It only takes an
already-produced rfc-to-api IR (api.ir.json, see design/rfc-to-api's
render_api.py for the full IR_SPEC) and:
  - resolves each operation's REST path/verb via the shared
    design/_shared/rest_path.py (the SAME derivation rfc-to-api's OpenAPI
    renderer uses, so the docs never show a different path than the spec)
  - resolves referenced entity field lists (from schema_ir or local shapes)
  - renders a Markdown skeleton: one heading per operation, a parameter/
    field table per input and output shape, an auth line, an error table
  - the LLM fills in `<DESCRIPTION>` and `<EXAMPLE>` placeholders left in
    the skeleton

Usage:
    render_docs.py --ir-file api.ir.json [--schema-ir-file schema.ir.json]
"""
import argparse
import json
import os
import sys

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# In the full repo, api-docs lives under implementation/ but needs
# design/_shared/ specifically (a different directory's content than
# implementation/_shared/). When this skill folder is copied standalone
# (as its own SKILL.md explicitly supports), the installer merges every
# category's shared/ content into one flat "_shared" sibling instead —
# so a plain "_shared" sibling must be tried too, not just the in-repo path.
for _candidate in (os.path.join(_PARENT_DIR, "..", "design", "_shared"), os.path.join(_PARENT_DIR, "_shared")):
    if os.path.isdir(_candidate):
        sys.path.insert(0, _candidate)
        break
from rest_path import derive_rest_path_verb  # noqa: E402


def resolve_entity_fields(entity_name, schema_ir, shapes):
    if schema_ir:
        for e in schema_ir.get("entities", []):
            if e["name"] == entity_name:
                return e.get("fields", [])
    for s in shapes or []:
        if s["name"] == entity_name:
            return s.get("fields", [])
    return None


def resolve_shape_fields(shape, schema_ir, shapes):
    """A field-list shape ({"fields": [...]}) or a ref-to-entity shape
    ({"type": "ref", "ref_entity": "X"})."""
    if shape is None:
        return []
    if shape.get("type") == "ref":
        return resolve_entity_fields(shape["ref_entity"], schema_ir, shapes) or []
    return shape.get("fields", [])


def field_type_label(field):
    ftype = field.get("type", "")
    if ftype == "ref":
        return f"ref({field.get('ref_entity', '?')})"
    if ftype == "array":
        return f"array<{field.get('item_type', '?')}>"
    if ftype == "enum":
        return f"enum({'|'.join(field.get('values', []))})"
    return ftype


def render_field_table(fields):
    if not fields:
        return "_No fields._\n"
    lines = ["| Field | Type | Required | Description |", "|---|---|---|---|"]
    for f in fields:
        required = "no" if f.get("nullable", False) else "yes"
        lines.append(
            f"| `{f['name']}` | {field_type_label(f)} | {required} | <EXAMPLE:description for {f['name']}> |"
        )
    return "\n".join(lines) + "\n"


def render_operation(op, schema_ir, shapes):
    path, verb, high_confidence = derive_rest_path_verb(op)
    confidence_note = "" if high_confidence else " _(path derivation: best guess, no `entity`/ref hint on this operation — verify)_"

    input_fields = op.get("input", {}).get("fields", [])
    output_fields = resolve_shape_fields(op.get("output", {}).get("shape"), schema_ir, shapes)

    lines = [f"### `{op['name']}`", "", f"`{verb} {path}`{confidence_note}", ""]
    lines.append(f"<DESCRIPTION: expand on \"{op.get('description', '')}\">")
    lines.append("")

    lines.append(f"**Auth required:** {'yes' if op.get('requires_auth') else 'no'}")
    if op.get("required_scopes"):
        lines.append(f"**Required scopes:** {', '.join(op['required_scopes'])}")
    lines.append(f"**Idempotent:** {'yes' if op.get('idempotent') else 'no'}")
    if op.get("paginated"):
        lines.append(f"**Paginated:** yes ({op.get('pagination_style', 'unspecified')})")
    lines.append("")

    lines.append("**Request fields**")
    lines.append("")
    lines.append(render_field_table(input_fields))
    lines.append("<EXAMPLE:request body>")
    lines.append("")

    lines.append(f"**Response** ({op.get('output', {}).get('cardinality', 'single')})")
    lines.append("")
    lines.append(render_field_table(output_fields))
    lines.append("<EXAMPLE:response body>")
    lines.append("")

    errors = op.get("errors", [])
    if errors:
        lines.append("**Errors**")
        lines.append("")
        lines.append("| Case | Status | Description |")
        lines.append("|---|---|---|")
        for e in errors:
            status = e.get("status_hint", "")
            lines.append(f"| `{e['case']}` | {status} | {e.get('description', '')} |")
        lines.append("")

    return "\n".join(lines)


def render_docs(ir, schema_ir=None):
    shapes = ir.get("shapes", [])
    sections = [render_operation(op, schema_ir, shapes) for op in ir.get("operations", [])]
    return "# API Reference\n\n<DESCRIPTION: one-paragraph overview of this API>\n\n" + "\n\n".join(sections) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ir-file", required=True)
    parser.add_argument("--schema-ir-file", default=None)
    args = parser.parse_args()

    with open(args.ir_file) as f:
        ir = json.load(f)

    schema_ir = None
    if args.schema_ir_file and os.path.isfile(args.schema_ir_file):
        with open(args.schema_ir_file) as f:
            schema_ir = json.load(f)

    print(render_docs(ir, schema_ir))


if __name__ == "__main__":
    sys.exit(main())
