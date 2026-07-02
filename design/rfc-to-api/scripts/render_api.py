#!/usr/bin/env python3
"""
Deterministic IR -> concrete-API renderer for rfc-to-api (stdlib only).

This script does NOT extract an API design from an RFC — that's LLM
judgment (reading prose, inferring operations, flagging assumptions). This
script only takes an already-produced protocol-neutral IR (see IR_SPEC
below) and:
  - validates its structural integrity (duplicate operation names, dangling
    entity refs, domain-specific errors missing a status hint)
  - renders it into concrete target formats: OpenAPI 3.1 (as JSON — no
    YAML, to stay stdlib-only) and GraphQL SDL

IR_SPEC (api.ir.json), informally:
{
  "version": "1.0",
  "entities_source": "schema.ir.json" | null,   # where ref'd entities live
  "shapes": [ {"name": "Post", "fields": [...]} ],  # locally-defined
                                                     # entities, used only
                                                     # when entities_source
                                                     # is null
  "operations": [
    {
      "name": "createPost",              # camelCase, protocol-agnostic
      "description": "...",
      "kind": "create"|"read"|"list"|"update"|"delete"|"action",
      "entity": "Post",                  # optional but STRONGLY recommended for
                                          # read/update/delete/action: the entity
                                          # this operation targets. Path derivation
                                          # falls back to scanning input/output refs
                                          # only when this is absent, which fails for
                                          # e.g. `delete` ops with no ref in either.
      "input": {"fields": [ ...field defs, same abstract type system as
                             rfc-to-schema's IR: uuid/string/text/int/
                             bigint/float/decimal/bool/datetime/date/json/
                             enum/object/array/ref ... ]},
      "output": {"cardinality": "single"|"collection",
                 "shape": {"type": "ref", "ref_entity": "Post"} |
                          {"fields": [...]}},
      "errors": [ {"case": "not_found"} |
                  {"case": "insufficient_credits", "status_hint": 402,
                   "description": "..."} ],
      "requires_auth": true,
      "required_scopes": ["posts:write"],
      "idempotent": false,
      "paginated": false,
      "pagination_style": "cursor"|"offset"|"page_number"|null,
      "rest_override": {"path": "/posts", "verb": "POST"},   # optional
      "graphql_override": {"type": "mutation", "field_name": "createPost"}
    }
  ]
}

Usage:
    render_api.py --ir-file api.ir.json [--schema-ir-file schema.ir.json] --target openapi|graphql|all
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_shared"))
from naming import slugify_table_name  # noqa: E402
from rest_path import derive_rest_path_verb, KIND_TO_VERB  # noqa: E402

VALID_KINDS = {"create", "read", "list", "update", "delete", "action"}

BASE_ERROR_STATUS = {
    "not_found": 404,
    "validation_failed": 422,
    "conflict": 409,
    "unauthorized": 401,
    "forbidden": 403,
    "rate_limited": 429,
    "internal_error": 500,
}

# ---------------------------------------------------------------------------
# Entity resolution (optional $ref into rfc-to-schema's IR, else local shapes)
# ---------------------------------------------------------------------------


def resolve_entity_fields(entity_name, schema_ir, shapes):
    if schema_ir:
        for e in schema_ir.get("entities", []):
            if e["name"] == entity_name:
                return e.get("fields", [])
    for s in shapes or []:
        if s["name"] == entity_name:
            return s.get("fields", [])
    return None


def _direct_referenced_entities(ir):
    """Walk every operation's input/output for type=='ref' fields (including
    nested object/array fields) and return the set of DIRECTLY referenced
    entity names — one hop only, not transitive."""
    names = set()

    def walk_fields(fields):
        for f in fields or []:
            if f.get("type") == "ref":
                names.add(f["ref_entity"])
            if f.get("type") == "object" or (f.get("type") == "array" and f.get("item_type") == "object"):
                walk_fields(f.get("fields"))

    for op in ir.get("operations", []):
        walk_fields(op.get("input", {}).get("fields"))
        output = op.get("output", {})
        shape = output.get("shape", {})
        if shape.get("type") == "ref":
            names.add(shape["ref_entity"])
        else:
            walk_fields(shape.get("fields"))
    return names


def collect_referenced_entities(ir, schema_ir=None, shapes=None):
    """Transitive closure of every entity name reachable from an operation's
    input/output — including entities only reached because an already-
    referenced entity has its OWN ref field to them (e.g. Bookmark has a
    `user_id: ref->User` field, but no operation mentions User directly).
    Without this closure, a renderer would emit `$ref`/type references to
    entities it never actually declares — invalid OpenAPI/GraphQL output."""
    shapes = shapes if shapes is not None else ir.get("shapes", [])
    seen = set()
    frontier = _direct_referenced_entities(ir)
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        fields = resolve_entity_fields(name, schema_ir, shapes) or []
        for f in fields:
            if f.get("type") == "ref" and f["ref_entity"] not in seen:
                frontier.add(f["ref_entity"])
    return seen


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_ir(ir: dict, schema_ir: dict = None):
    errors = []
    ops = ir.get("operations", [])
    names = [op["name"] for op in ops]
    seen = set()
    for n in names:
        if n in seen:
            errors.append(f"duplicate operation name: {n}")
        seen.add(n)

    for op in ops:
        oname = op.get("name", "<unnamed>")
        kind = op.get("kind")
        if kind not in VALID_KINDS:
            errors.append(f"{oname}: unknown kind '{kind}'")

        for err in op.get("errors", []):
            case = err.get("case")
            if case not in BASE_ERROR_STATUS and not err.get("status_hint"):
                errors.append(f"{oname}: domain-specific error '{case}' is missing a required status_hint")

    shapes = ir.get("shapes", [])
    referenced = collect_referenced_entities(ir, schema_ir, shapes)
    for entity_name in referenced:
        if resolve_entity_fields(entity_name, schema_ir, shapes) is None:
            errors.append(
                f"unresolved entity ref '{entity_name}': not found in "
                f"schema_ir entities or ir.shapes"
            )

    return errors


# ---------------------------------------------------------------------------
# Path/verb derivation (REST)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# OpenAPI type mapping
# ---------------------------------------------------------------------------

OPENAPI_TYPE_MAP = {
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


def openapi_field_schema(field: dict) -> dict:
    ftype = field["type"]
    if ftype == "string" and field.get("max_length"):
        node = {"type": "string", "maxLength": field["max_length"]}
    elif ftype == "enum":
        node = {"type": "string", "enum": field["values"]}
    elif ftype == "ref":
        node = {"$ref": f"#/components/schemas/{field['ref_entity']}"}
    elif ftype == "object":
        node = {
            "type": "object",
            "properties": {f["name"]: openapi_field_schema(f) for f in field.get("fields", [])},
        }
    elif ftype == "array":
        item = field.get("item_type")
        if item == "object":
            item_node = {
                "type": "object",
                "properties": {f["name"]: openapi_field_schema(f) for f in field.get("fields", [])},
            }
        else:
            item_node = OPENAPI_TYPE_MAP.get(item, {"type": "string"})
        node = {"type": "array", "items": item_node}
    else:
        node = dict(OPENAPI_TYPE_MAP.get(ftype, {"type": "string"}))

    if field.get("assumed"):
        node["x-assumed"] = True
        node["x-assumed-reason"] = field.get("assumed_reason") or "not specified in RFC"
    return node


def entity_openapi_schema(entity_name: str, schema_ir, shapes) -> dict:
    fields = resolve_entity_fields(entity_name, schema_ir, shapes) or []
    return {
        "type": "object",
        "properties": {f["name"]: openapi_field_schema(f) for f in fields},
        "required": [f["name"] for f in fields if not f.get("nullable", True)],
    }


# ---------------------------------------------------------------------------
# OpenAPI rendering
# ---------------------------------------------------------------------------


def render_openapi(ir: dict, schema_ir=None) -> dict:
    shapes = ir.get("shapes", [])
    referenced = collect_referenced_entities(ir, schema_ir, shapes)
    schemas = {name: entity_openapi_schema(name, schema_ir, shapes) for name in sorted(referenced)}

    paths = {}
    needs_bearer_auth = False

    for op in ir.get("operations", []):
        path, verb, confident = derive_rest_path_verb(op)
        verb_l = verb.lower()
        paths.setdefault(path, {})

        parameters = []
        if "{id}" in path:
            parameters.append({"name": "id", "in": "path", "required": True, "schema": {"type": "string"}})
        if op.get("paginated"):
            style = op.get("pagination_style") or "cursor"
            if style == "cursor":
                parameters.append({"name": "cursor", "in": "query", "required": False, "schema": {"type": "string"}})
            elif style == "offset":
                parameters.append({"name": "offset", "in": "query", "required": False, "schema": {"type": "integer"}})
            else:
                parameters.append({"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}})
            parameters.append({"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}})

        operation_obj = {
            "operationId": op["name"],
            "summary": op.get("description") or op["name"],
        }
        if not confident:
            operation_obj["x-path-derivation-confidence"] = "low"
        if parameters:
            operation_obj["parameters"] = parameters

        input_fields = op.get("input", {}).get("fields", [])
        if input_fields and op["kind"] in ("create", "update", "action"):
            operation_obj["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {f["name"]: openapi_field_schema(f) for f in input_fields},
                            "required": [f["name"] for f in input_fields if not f.get("nullable", True)],
                        }
                    }
                },
            }

        responses = {}
        success_code = "201" if op["kind"] == "create" else "200"
        output = op.get("output", {})
        shape = output.get("shape", {})
        if shape.get("type") == "ref":
            body_schema = {"$ref": f"#/components/schemas/{shape['ref_entity']}"}
        elif shape.get("fields"):
            body_schema = {
                "type": "object",
                "properties": {f["name"]: openapi_field_schema(f) for f in shape["fields"]},
            }
        else:
            body_schema = None
        if body_schema and output.get("cardinality") == "collection":
            body_schema = {"type": "array", "items": body_schema}
        if op["kind"] == "delete":
            responses["204"] = {"description": "Deleted"}
        elif body_schema:
            responses[success_code] = {
                "description": "Success",
                "content": {"application/json": {"schema": body_schema}},
            }
        else:
            responses[success_code] = {"description": "Success"}

        for err in op.get("errors", []):
            case = err["case"]
            status = str(err.get("status_hint") or BASE_ERROR_STATUS.get(case, 500))
            responses[status] = {"description": err.get("description") or case}

        operation_obj["responses"] = responses

        if op.get("requires_auth"):
            needs_bearer_auth = True
            operation_obj["security"] = [{"bearerAuth": []}]
            if op.get("required_scopes"):
                operation_obj["x-required-scopes"] = op["required_scopes"]

        paths[path][verb_l] = operation_obj

    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Generated API", "version": "0.1.0"},
        "paths": paths,
        "components": {"schemas": schemas},
    }
    if needs_bearer_auth:
        spec["components"]["securitySchemes"] = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    return spec


# ---------------------------------------------------------------------------
# GraphQL SDL rendering
# ---------------------------------------------------------------------------

GRAPHQL_SCALAR_MAP = {
    "uuid": "ID",
    "string": "String",
    "text": "String",
    "int": "Int",
    "bigint": "Int",
    "float": "Float",
    "decimal": "Float",
    "bool": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "json": "JSON",
}

CUSTOM_SCALARS = {"datetime": "DateTime", "date": "Date", "json": "JSON"}


def to_camel_case(name: str) -> str:
    """snake_case or already-camelCase -> camelCase (GraphQL field-name idiom)."""
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def to_pascal_case(name: str) -> str:
    camel = to_camel_case(name)
    return camel[:1].upper() + camel[1:]


def enum_type_name(owner_name: str, field_name: str) -> str:
    return f"{owner_name}{to_pascal_case(field_name)}Enum"


def graphql_type_for_field(field: dict, for_input: bool, owner_name: str = "") -> str:
    ftype = field["type"]
    if ftype == "ref":
        base = "ID" if for_input else field["ref_entity"]
    elif ftype == "enum":
        base = enum_type_name(owner_name, field["name"])
    elif ftype == "array":
        item = field.get("item_type")
        item_type = "ID" if item == "ref" else GRAPHQL_SCALAR_MAP.get(item, item or "String")
        base = f"[{item_type}!]"
    elif ftype == "object":
        base = "JSON"
    else:
        base = GRAPHQL_SCALAR_MAP.get(ftype, "String")
    if not field.get("nullable", True):
        base = f"{base}!"
    return base


def collect_custom_scalars(all_fields):
    used = set()
    for f in all_fields:
        if f.get("type") in CUSTOM_SCALARS:
            used.add(CUSTOM_SCALARS[f["type"]])
        if f.get("type") == "array" and f.get("item_type") in CUSTOM_SCALARS:
            used.add(CUSTOM_SCALARS[f["item_type"]])
    return used


def collect_enum_types(owner_field_groups):
    """owner_field_groups: list of (owner_name, fields). Returns {enum_type_name: values},
    so every `enum`-typed field referenced anywhere gets a real `enum X { ... }` declaration
    — a field type that references an undeclared type is invalid GraphQL SDL."""
    enums = {}
    for owner_name, fields in owner_field_groups:
        for f in fields:
            if f.get("type") == "enum":
                enums[enum_type_name(owner_name, f["name"])] = f["values"]
    return enums


def render_fields_block(fields, for_input: bool, owner_name: str) -> str:
    return "\n".join(
        f"  {to_camel_case(f['name'])}: {graphql_type_for_field(f, for_input, owner_name)}"
        for f in fields
    )


def render_graphql(ir: dict, schema_ir=None) -> str:
    shapes = ir.get("shapes", [])
    referenced = sorted(collect_referenced_entities(ir, schema_ir, shapes))
    entity_fields = {name: resolve_entity_fields(name, schema_ir, shapes) or [] for name in referenced}

    owner_field_groups = [(name, fields) for name, fields in entity_fields.items()]
    for op in ir.get("operations", []):
        input_fields = op.get("input", {}).get("fields", [])
        if input_fields:
            owner_field_groups.append((to_pascal_case(op["name"]) + "Input", input_fields))

    all_fields_flat = [f for _, fields in owner_field_groups for f in fields]
    scalars = collect_custom_scalars(all_fields_flat)
    enums = collect_enum_types(owner_field_groups)

    blocks = []
    for s in sorted(scalars):
        blocks.append(f"scalar {s}")
    if scalars:
        blocks.append("")

    for enum_name, values in sorted(enums.items()):
        values_block = "\n".join(f"  {v.upper()}" for v in values)
        blocks.append(f"enum {enum_name} {{\n{values_block}\n}}")

    blocks.append("type Error {\n  code: String!\n  message: String\n}")
    blocks.append("type PageInfo {\n  hasNextPage: Boolean!\n  endCursor: String\n}")

    for name in referenced:
        field_lines = render_fields_block(entity_fields[name], for_input=False, owner_name=name)
        blocks.append(f"type {name} {{\n{field_lines}\n}}")

    query_fields = []
    mutation_fields = []
    extra_types = []

    for op in ir.get("operations", []):
        gtype, field_name = _graphql_field_placement(op)
        args = _graphql_args(op)
        return_type = _graphql_return_type(op, extra_types)
        line = f"  {field_name}({args}): {return_type}" if args else f"  {field_name}: {return_type}"
        if gtype == "query":
            query_fields.append(line)
        else:
            mutation_fields.append(line)

        input_fields = op.get("input", {}).get("fields", [])
        if input_fields and op["kind"] in ("create", "update"):
            input_type_name = to_pascal_case(field_name) + "Input"
            owner_name = to_pascal_case(op["name"]) + "Input"
            body = render_fields_block(input_fields, for_input=True, owner_name=owner_name)
            extra_types.append(f"input {input_type_name} {{\n{body}\n}}")

    if query_fields:
        blocks.append("type Query {\n" + "\n".join(query_fields) + "\n}")
    if mutation_fields:
        blocks.append("type Mutation {\n" + "\n".join(mutation_fields) + "\n}")

    blocks.extend(extra_types)

    return "\n\n".join(blocks) + "\n"


def _graphql_field_placement(op: dict):
    override = op.get("graphql_override")
    if override:
        return override["type"], override["field_name"]
    gtype = "query" if op["kind"] in ("read", "list") else "mutation"
    return gtype, op["name"]


def _graphql_args(op: dict) -> str:
    args = []
    if "{id}" in derive_rest_path_verb(op)[0] and op["kind"] != "create":
        args.append("id: ID!")
    input_fields = op.get("input", {}).get("fields", [])
    if input_fields and op["kind"] in ("create", "update"):
        field_name = _graphql_field_placement(op)[1]
        input_type_name = field_name[0].upper() + field_name[1:] + "Input"
        args.append(f"input: {input_type_name}!")
    if op.get("paginated"):
        style = op.get("pagination_style") or "cursor"
        if style == "cursor":
            args.append("cursor: String")
        elif style == "offset":
            args.append("offset: Int")
        else:
            args.append("page: Int")
        args.append("limit: Int")
    return ", ".join(args)


def _graphql_return_type(op: dict, extra_types_accum: list) -> str:
    output = op.get("output", {})
    shape = output.get("shape", {})

    if shape.get("type") == "ref":
        base_type = shape["ref_entity"]
    elif shape.get("fields"):
        # inline (non-ref) output shape with real fields -> emit a dedicated
        # named type instead of collapsing to a bare JSON scalar, which would
        # both discard structure and produce a nonsensical payload field name
        base_type = to_pascal_case(op["name"]) + "Result"
        if not any(f"type {base_type} " in t for t in extra_types_accum):
            body = render_fields_block(shape["fields"], for_input=False, owner_name=base_type)
            extra_types_accum.append(f"type {base_type} {{\n{body}\n}}")
    else:
        base_type = "JSON"

    if output.get("cardinality") == "collection":
        if op.get("paginated") and (op.get("pagination_style") or "cursor") == "cursor":
            conn_name = f"{base_type}Connection"
            edge_name = f"{base_type}Edge"
            if not any(conn_name in t for t in extra_types_accum):
                extra_types_accum.append(
                    f"type {edge_name} {{\n  node: {base_type}!\n  cursor: String!\n}}"
                )
                extra_types_accum.append(
                    f"type {conn_name} {{\n  edges: [{edge_name}!]!\n  pageInfo: PageInfo!\n}}"
                )
            return conn_name
        return f"[{base_type}!]!"

    if op.get("errors"):
        payload_name = to_pascal_case(op["name"]) + "Payload"
        # bare scalar fallback (e.g. a delete op with no output shape at all)
        # has no natural field name to derive by lowercasing its first letter
        # ("JSON" -> "jSON" is nonsense) — use a generic "data" field instead
        bare_scalars = set(GRAPHQL_SCALAR_MAP.values()) | {"JSON"}
        data_field = "data" if base_type in bare_scalars else (base_type[:1].lower() + base_type[1:])
        if not any(f"type {payload_name} " in t for t in extra_types_accum):
            extra_types_accum.append(
                f"type {payload_name} {{\n  {data_field}: {base_type}\n  errors: [Error!]\n}}"
            )
        return payload_name

    return base_type


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="Render an API IR into concrete formats")
    ap.add_argument("--ir-file", required=True, help="Path to api.ir.json")
    ap.add_argument("--schema-ir-file", help="Optional path to a sibling schema.ir.json (rfc-to-schema)")
    ap.add_argument("--target", choices=["openapi", "graphql", "all"], default="all")
    args = ap.parse_args()

    with open(args.ir_file) as f:
        ir = json.load(f)

    schema_ir = None
    if args.schema_ir_file:
        with open(args.schema_ir_file) as f:
            schema_ir = json.load(f)

    errors = validate_ir(ir, schema_ir)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        sys.exit(1)

    result = {"valid": True}
    if args.target in ("openapi", "all"):
        result["openapi"] = render_openapi(ir, schema_ir)
    if args.target in ("graphql", "all"):
        result["graphql"] = render_graphql(ir, schema_ir)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
