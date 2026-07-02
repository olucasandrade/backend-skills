#!/usr/bin/env python3
"""
Deterministic IR -> concrete-schema renderer for rfc-to-schema (stdlib only).

This script does NOT extract a schema from an RFC — that's LLM judgment
(reading prose, inferring entities/fields, flagging assumptions). This
script only takes an already-produced IR (see IR_SPEC below) and:
  - validates its structural integrity (duplicate names, dangling refs)
  - renders it into concrete target formats: SQL DDL (Postgres-flavored)
    and JSON Schema

IR_SPEC (schema.ir.json), informally:
{
  "version": "1.0",
  "entities": [
    {
      "name": "User",                  # required, PascalCase logical name
      "table_name": "users",           # optional; slugified from name if absent
      "description": "...",            # optional
      "fields": [
        {
          "name": "id",
          "type": "uuid" | "string" | "text" | "int" | "bigint" | "float" |
                  "decimal" | "bool" | "datetime" | "date" | "json" |
                  "enum" | "object" | "array" | "ref",
          "nullable": false,
          "primary_key": false,
          "unique": false,
          "default": null,             # raw default expression, renderer-specific
          "max_length": null,          # for "string"
          "values": [...],             # for "enum"
          "item_type": "string",       # for "array" (a type name, or "object")
          "fields": [...],             # for "object" or array<object> (nested field list)
          "ref_entity": "Post",        # for "ref"
          "cardinality": "many_to_one" | "one_to_one",  # for "ref"
          "assumed": false,            # true if this field/detail was inferred, not stated
          "assumed_reason": null       # human-readable reason when assumed=true
        }
      ],
      "unique_constraints": [           # optional; composite/multi-column
                                         # uniqueness — a single-field
                                         # `unique: true` above CANNOT
                                         # express "these two columns
                                         # together must be unique" (e.g. a
                                         # user can only bookmark a given
                                         # post once), which is common
                                         # enough to need its own concept
        ["user_id", "post_id"]
      ]
    }
  ],
  "relationships": [                   # many-to-many only; 1:1 / N:1 are `ref` fields
    {"between": ["Post", "Tag"], "join_table": "post_tags"}
  ]
}

Usage:
    render_schema.py --ir-file schema.ir.json --target sql|json-schema|all
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_shared"))
from naming import slugify_table_name  # noqa: E402

SCALAR_TYPES = {
    "uuid", "string", "text", "int", "bigint", "float", "decimal",
    "bool", "datetime", "date", "json",
}
STRUCTURAL_TYPES = {"enum", "object", "array", "ref"}
VALID_TYPES = SCALAR_TYPES | STRUCTURAL_TYPES


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_ir(ir: dict):
    """Return a list of human-readable structural error strings (empty = valid)."""
    errors = []
    entities = ir.get("entities", [])
    entity_names = [e["name"] for e in entities]

    seen = set()
    for name in entity_names:
        if name in seen:
            errors.append(f"duplicate entity name: {name}")
        seen.add(name)

    entity_name_set = set(entity_names)

    for entity in entities:
        ename = entity.get("name", "<unnamed>")
        field_names = [f["name"] for f in entity.get("fields", [])]
        seen_fields = set()
        for fname in field_names:
            if fname in seen_fields:
                errors.append(f"{ename}: duplicate field name '{fname}'")
            seen_fields.add(fname)

        for field in entity.get("fields", []):
            errors.extend(_validate_field(ename, field, entity_name_set))

        for constraint in entity.get("unique_constraints", []):
            if len(constraint) < 2:
                errors.append(f"{ename}: unique_constraints entry {constraint!r} needs at least 2 fields (use per-field 'unique' for a single column)")
            for fname in constraint:
                if fname not in seen_fields:
                    errors.append(f"{ename}: unique_constraints references unknown field '{fname}'")

    for rel in ir.get("relationships", []):
        between = rel.get("between", [])
        if len(between) != 2:
            errors.append(f"relationship must name exactly 2 entities: {rel}")
            continue
        for e in between:
            if e not in entity_name_set:
                errors.append(f"relationship references unknown entity: {e}")

    return errors


def _validate_field(entity_name, field, entity_name_set):
    errors = []
    ftype = field.get("type")
    fname = field.get("name", "<unnamed>")
    if ftype not in VALID_TYPES:
        errors.append(f"{entity_name}.{fname}: unknown type '{ftype}'")
        return errors
    if ftype == "ref":
        target = field.get("ref_entity")
        if target not in entity_name_set:
            errors.append(f"{entity_name}.{fname}: ref to unknown entity '{target}'")
    if ftype == "enum" and not field.get("values"):
        errors.append(f"{entity_name}.{fname}: enum field has no 'values'")
    if ftype == "array" and not field.get("item_type"):
        errors.append(f"{entity_name}.{fname}: array field has no 'item_type'")
    if ftype in ("object",) or (ftype == "array" and field.get("item_type") == "object"):
        for nested in field.get("fields", []):
            errors.extend(_validate_field(f"{entity_name}.{fname}", nested, entity_name_set))
    return errors


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def table_name_for(entity: dict) -> str:
    return entity.get("table_name") or slugify_table_name(entity["name"])


# ---------------------------------------------------------------------------
# SQL DDL rendering (Postgres-flavored)
# ---------------------------------------------------------------------------

SQL_TYPE_MAP = {
    "uuid": "UUID",
    "text": "TEXT",
    "int": "INTEGER",
    "bigint": "BIGINT",
    "float": "DOUBLE PRECISION",
    "decimal": "NUMERIC",
    "bool": "BOOLEAN",
    "datetime": "TIMESTAMPTZ",
    "date": "DATE",
    "json": "JSONB",
}


def sql_type_for_field(field: dict, table_by_entity: dict) -> str:
    ftype = field["type"]
    if ftype == "string":
        max_len = field.get("max_length")
        return f"VARCHAR({max_len})" if max_len else "VARCHAR"
    if ftype == "enum":
        return "TEXT"  # rendered with a CHECK constraint separately, not a native PG ENUM (portability)
    if ftype == "ref":
        return "UUID"  # assumes UUID-keyed entities; matches default PK type below
    if ftype == "object":
        return "JSONB"
    if ftype == "array":
        item = field.get("item_type")
        if item in SQL_TYPE_MAP or item == "string":
            return (SQL_TYPE_MAP.get(item, "VARCHAR") if item != "string" else "VARCHAR") + "[]"
        return "JSONB"  # array of objects/refs -> not representable as a native array
    return SQL_TYPE_MAP.get(ftype, "TEXT")


def render_field_comment(field: dict) -> str:
    if field.get("assumed"):
        reason = field.get("assumed_reason") or "not specified in RFC"
        return f"  -- ASSUMED: {reason}"
    return ""


def render_sql(ir: dict) -> str:
    entities = ir.get("entities", [])
    table_by_entity = {e["name"]: table_name_for(e) for e in entities}
    out = []

    for entity in entities:
        table = table_by_entity[entity["name"]]
        lines = [f"CREATE TABLE {table} ("]
        entries = []  # list of (line_without_trailing_comma, trailing_comment)
        for field in entity.get("fields", []):
            entries.append(_render_sql_column(field, table_by_entity))
            if field["type"] == "enum":
                values = ", ".join(f"'{v}'" for v in field["values"])
                entries.append((
                    f"  CONSTRAINT chk_{table}_{field['name']} CHECK ({field['name']} IN ({values}))",
                    "",
                ))
        for constraint in entity.get("unique_constraints", []):
            cols = ", ".join(constraint)
            name = "_".join(constraint)
            entries.append((
                f"  CONSTRAINT uq_{table}_{name} UNIQUE ({cols})",
                "",
            ))
        # comma must precede any trailing `--` comment, or the comment
        # swallows the comma and merges two columns into invalid SQL
        body = []
        for i, (line, comment) in enumerate(entries):
            comma = "," if i < len(entries) - 1 else ""
            body.append(f"{line}{comma}{comment}")
        lines.append("\n".join(body))
        lines.append(");")
        if entity.get("description"):
            lines.insert(0, f"-- {entity['description']}")
        out.append("\n".join(lines))

    for rel in ir.get("relationships", []):
        a, b = rel["between"]
        join_table = rel.get("join_table") or f"{table_by_entity[a]}_{table_by_entity[b]}"
        out.append(
            f"CREATE TABLE {join_table} (\n"
            f"  {slugify_table_name(a)[:-1]}_id UUID NOT NULL REFERENCES {table_by_entity[a]}(id),\n"
            f"  {slugify_table_name(b)[:-1]}_id UUID NOT NULL REFERENCES {table_by_entity[b]}(id),\n"
            f"  PRIMARY KEY ({slugify_table_name(a)[:-1]}_id, {slugify_table_name(b)[:-1]}_id)\n"
            f");"
        )

    return "\n\n".join(out) + "\n"


def _render_sql_column(field: dict, table_by_entity: dict):
    """Return (line_without_trailing_comma_or_comment, trailing_comment)."""
    parts = [f"  {field['name']}", sql_type_for_field(field, table_by_entity)]
    if field.get("primary_key"):
        parts.append("PRIMARY KEY")
    if not field.get("nullable", True) and not field.get("primary_key"):
        parts.append("NOT NULL")
    if field.get("unique") and not field.get("primary_key"):
        parts.append("UNIQUE")
    if field.get("type") == "ref":
        ref_table = table_by_entity.get(field["ref_entity"], field["ref_entity"])
        parts.append(f"REFERENCES {ref_table}(id)")
    if field.get("default") is not None:
        parts.append(f"DEFAULT {field['default']}")
    return " ".join(parts), render_field_comment(field)


# ---------------------------------------------------------------------------
# JSON Schema rendering
# ---------------------------------------------------------------------------

JSON_SCHEMA_TYPE_MAP = {
    "uuid": {"type": "string", "format": "uuid"},
    "string": {"type": "string"},
    "text": {"type": "string"},
    "int": {"type": "integer"},
    "bigint": {"type": "integer"},
    "float": {"type": "number"},
    "decimal": {"type": "number"},
    "bool": {"type": "boolean"},
    "datetime": {"type": "string", "format": "date-time"},
    "date": {"type": "string", "format": "date"},
    "json": {"type": "object"},
}


def _render_json_schema_field(field: dict) -> dict:
    ftype = field["type"]
    if ftype == "string" and field.get("max_length"):
        node = {"type": "string", "maxLength": field["max_length"]}
    elif ftype == "enum":
        node = {"type": "string", "enum": field["values"]}
    elif ftype == "ref":
        node = {"$ref": f"#/$defs/{field['ref_entity']}"}
    elif ftype == "object":
        node = {
            "type": "object",
            "properties": {f["name"]: _render_json_schema_field(f) for f in field.get("fields", [])},
            "required": [f["name"] for f in field.get("fields", []) if not f.get("nullable", True)],
        }
    elif ftype == "array":
        item = field.get("item_type")
        if item == "object":
            item_node = {
                "type": "object",
                "properties": {f["name"]: _render_json_schema_field(f) for f in field.get("fields", [])},
            }
        else:
            item_node = JSON_SCHEMA_TYPE_MAP.get(item, {"type": "string"})
        node = {"type": "array", "items": item_node}
    else:
        node = dict(JSON_SCHEMA_TYPE_MAP.get(ftype, {"type": "string"}))

    if field.get("assumed"):
        node["x-assumed"] = True
        node["x-assumed-reason"] = field.get("assumed_reason") or "not specified in RFC"
    return node


def render_json_schema(ir: dict) -> dict:
    defs = {}
    for entity in ir.get("entities", []):
        properties = {}
        required = []
        for field in entity.get("fields", []):
            properties[field["name"]] = _render_json_schema_field(field)
            if not field.get("nullable", True):
                required.append(field["name"])
        schema_def = {
            "type": "object",
            "description": entity.get("description"),
            "properties": properties,
            "required": required,
        }
        if entity.get("unique_constraints"):
            # informational only — plain JSON Schema has no native way to
            # enforce cross-field uniqueness, unlike SQL's UNIQUE(...)
            schema_def["x-unique-constraints"] = entity["unique_constraints"]
        defs[entity["name"]] = schema_def
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": defs,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="Render a schema IR into concrete formats")
    ap.add_argument("--ir-file", required=True, help="Path to schema.ir.json")
    ap.add_argument("--target", choices=["sql", "json-schema", "all"], default="all")
    args = ap.parse_args()

    with open(args.ir_file) as f:
        ir = json.load(f)

    errors = validate_ir(ir)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        sys.exit(1)

    result = {"valid": True}
    if args.target in ("sql", "all"):
        result["sql"] = render_sql(ir)
    if args.target in ("json-schema", "all"):
        result["json_schema"] = render_json_schema(ir)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
