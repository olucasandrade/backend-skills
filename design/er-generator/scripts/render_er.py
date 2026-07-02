#!/usr/bin/env python3
"""
Deterministic ER-diagram engine for er-generator (stdlib only).

Unlike rfc-to-schema/rfc-to-api, there's no prose to interpret here — every
input source (a schema IR, a live SQLite file, static SQL, a Postgres/MySQL
introspection query result) is already structured. So this script does
nearly everything: source parsing, projecting down to a lightweight
ER-native representation, clustering oversized schemas, and rendering
Mermaid. The calling skill mostly orchestrates (which source, ambiguity
resolution, never auto-connecting to a live remote DB) rather than judging.

ER_SPEC (the lightweight, source-agnostic internal representation), informally:
{
  "entities": [
    {"name": "User", "fields": [
        {"name": "id", "type": "uuid", "pk": true, "nullable": false},
        {"name": "email", "type": "string", "nullable": false},
        {"name": "role", "type": "enum", "values": ["admin", "member"], "nullable": false}
    ]}
  ],
  "relationships": [
    {"from": "Post", "to": "User", "field": "author_id",
     "cardinality": "many_to_one", "nullable": false},
    {"from": "Post", "to": "Tag", "cardinality": "many_to_many", "join_table": "post_tags"}
  ]
}

This is deliberately NOT the same shape as rfc-to-schema's schema.ir.json —
that IR carries RFC-extraction concepts (assumed/assumed_reason, defaults,
max_length) meaningless for something read directly off a live database.
schema.ir.json is projected DOWN into this shape; the reverse never happens.

Usage:
    render_er.py --er-file er.json [--max-entities N] --target mermaid
    (er.json is the lightweight ER representation above; use the helper
    functions directly — project_schema_ir, parse_create_table_sql,
    parse_sqlite_file, parse_introspection_rows — to produce one from a
    given source before rendering)
"""

import argparse
import json
import re
import sqlite3
import sys

MERMAID_TYPE_MAP = {
    "uuid": "uuid",
    "string": "string",
    "text": "string",
    "int": "int",
    "bigint": "int",
    "float": "float",
    "decimal": "float",
    "bool": "boolean",
    "datetime": "datetime",
    "date": "date",
    "json": "json",
    "object": "json",
    "array": "array",
    # a `ref` field is a foreign key column; this repo's convention (see
    # rfc-to-schema) defaults primary keys to uuid, so that's a reasonable
    # rendering default here too — better than silently falling through to
    # the generic "string" default, which would misrepresent an FK column
    "ref": "uuid",
}

VALID_CARDINALITY_SYMBOLS = {"||--||", "||--o{", "|o--o{", "}o--o{", "|o--||"}


# ---------------------------------------------------------------------------
# Projection: rfc-to-schema's schema.ir.json -> lightweight ER representation
# ---------------------------------------------------------------------------


def project_schema_ir(schema_ir: dict) -> dict:
    entities = []
    relationships = []

    for entity in schema_ir.get("entities", []):
        fields = []
        for f in entity.get("fields", []):
            if f["type"] == "ref":
                relationships.append({
                    "from": entity["name"],
                    "to": f["ref_entity"],
                    "field": f["name"],
                    "cardinality": "many_to_one",
                    "nullable": f.get("nullable", True),
                })
                fields.append({"name": f["name"], "type": "ref", "nullable": f.get("nullable", True)})
                continue
            field_out = {"name": f["name"], "type": f["type"], "nullable": f.get("nullable", True)}
            if f.get("primary_key"):
                field_out["pk"] = True
            if f.get("values"):
                field_out["values"] = f["values"]
            fields.append(field_out)
        entities.append({"name": entity["name"], "fields": fields})

    for rel in schema_ir.get("relationships", []):
        a, b = rel["between"]
        relationships.append({
            "from": a, "to": b,
            "cardinality": "many_to_many",
            "join_table": rel.get("join_table"),
        })

    return {"entities": entities, "relationships": relationships}


# ---------------------------------------------------------------------------
# SQLite introspection (stdlib sqlite3, genuinely "live" — no CLI needed)
# ---------------------------------------------------------------------------


def parse_sqlite_file(path: str) -> dict:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        table_names = [r[0] for r in cur.fetchall()]

        entities = []
        relationships = []
        for table in table_names:
            cur.execute(f"PRAGMA table_info('{table}')")
            fields = []
            for row in cur.fetchall():
                # row: cid, name, type, notnull, dflt_value, pk
                _, name, coltype, notnull, _, pk = row
                field = {
                    "name": name,
                    "type": _sqlite_type_to_abstract(coltype),
                    "nullable": not bool(notnull),
                }
                if pk:
                    field["pk"] = True
                fields.append(field)
            entities.append({"name": table, "fields": fields})

            cur.execute(f"PRAGMA foreign_key_list('{table}')")
            for fk_row in cur.fetchall():
                # row: id, seq, table, from, to, on_update, on_delete, match
                _, _, ref_table, from_col, _, *_ = fk_row
                relationships.append({
                    "from": table, "to": ref_table, "field": from_col,
                    "cardinality": "many_to_one", "nullable": True,
                })
        return {"entities": entities, "relationships": relationships}
    finally:
        conn.close()


def _sqlite_type_to_abstract(sqlite_type: str) -> str:
    t = (sqlite_type or "").upper()
    if "INT" in t:
        return "int"
    if "CHAR" in t or "TEXT" in t or "CLOB" in t:
        return "string"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "float"
    if "BOOL" in t:
        return "bool"
    if "DATE" in t:
        return "datetime"
    return "string"


# ---------------------------------------------------------------------------
# Static SQL parsing — documented CREATE TABLE subset, loud partial failure
# ---------------------------------------------------------------------------

CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?[\"'`]?(\w+)[\"'`]?\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
COLUMN_LINE_RE = re.compile(
    r"^\s*[\"'`]?(\w+)[\"'`]?\s+([A-Za-z][A-Za-z0-9_]*)(?:\(([^)]*)\))?\s*(.*)$"
)
SQL_TYPE_TO_ABSTRACT = {
    "UUID": "uuid", "VARCHAR": "string", "CHAR": "string", "TEXT": "string",
    "INTEGER": "int", "INT": "int", "BIGINT": "int", "SMALLINT": "int",
    "FLOAT": "float", "DOUBLE": "float", "REAL": "float", "NUMERIC": "float", "DECIMAL": "float",
    "BOOLEAN": "bool", "BOOL": "bool",
    "TIMESTAMPTZ": "datetime", "TIMESTAMP": "datetime", "DATETIME": "datetime",
    "DATE": "date", "JSONB": "json", "JSON": "json",
}
SKIP_LINE_PREFIXES = ("CONSTRAINT", "PRIMARY KEY(", "PRIMARY KEY (", "UNIQUE(", "UNIQUE (", "CHECK(", "CHECK (", "FOREIGN KEY")


def parse_create_table_sql(sql_text: str) -> tuple:
    """Returns (er_dict, report). report = {"parsed": [table names],
    "skipped": [{"table_or_statement": ..., "reason": ...}]} — never
    silently mis-parses; unrecognized statements/columns are reported, not guessed."""
    entities = []
    relationships = []
    parsed_tables = []
    skipped = []

    for match in CREATE_TABLE_RE.finditer(sql_text):
        table_name = match.group(1)
        body = match.group(2)
        fields = []
        table_ok = True
        for raw_line in _split_column_lines(body):
            line = raw_line.strip().rstrip(",").strip()
            if not line:
                continue
            if any(line.upper().startswith(p) for p in SKIP_LINE_PREFIXES):
                continue  # table-level constraints, not columns — not an error
            col_match = COLUMN_LINE_RE.match(line)
            if not col_match:
                skipped.append({"table_or_statement": f"{table_name} (column)", "reason": f"unparseable column line: {line!r}"})
                table_ok = False
                continue
            col_name, col_type, _, rest = col_match.groups()
            abstract_type = SQL_TYPE_TO_ABSTRACT.get(col_type.upper())
            if abstract_type is None:
                skipped.append({"table_or_statement": f"{table_name}.{col_name}", "reason": f"unrecognized SQL type: {col_type!r}"})
                table_ok = False
                continue
            field = {
                "name": col_name,
                "type": abstract_type,
                "nullable": "NOT NULL" not in rest.upper(),
            }
            if "PRIMARY KEY" in rest.upper():
                field["pk"] = True
            ref_match = re.search(r"REFERENCES\s+[\"'`]?(\w+)[\"'`]?", rest, re.IGNORECASE)
            if ref_match:
                relationships.append({
                    "from": table_name, "to": ref_match.group(1), "field": col_name,
                    "cardinality": "many_to_one", "nullable": field["nullable"],
                })
            fields.append(field)
        entities.append({"name": table_name, "fields": fields})
        if table_ok:
            parsed_tables.append(table_name)

    report = {"parsed": parsed_tables, "skipped": skipped}
    return {"entities": entities, "relationships": relationships}, report


def _split_column_lines(body: str):
    """Split a CREATE TABLE body on top-level commas (not inside parens)."""
    lines, depth, current = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            lines.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        lines.append("".join(current))
    return lines


# ---------------------------------------------------------------------------
# Postgres/MySQL introspection — parses OUR OWN pipe-delimited query output,
# not arbitrary `\d` catalog output. The actual shell-out (running psql/mysql
# with this query) is the calling skill's job, only with explicit connection
# details; this function only parses the resulting text.
# ---------------------------------------------------------------------------

INTROSPECTION_QUERY_POSTGRES = (
    "SELECT c.table_name, c.column_name, c.data_type, c.is_nullable, "
    "COALESCE(pk.is_pk, 'NO'), COALESCE(fk.ref_table, ''), COALESCE(fk.ref_column, '') "
    "FROM information_schema.columns c "
    "LEFT JOIN (...) pk ON ... LEFT JOIN (...) fk ON ... "
    "ORDER BY c.table_name, c.ordinal_position;"
)  # illustrative; the exact catalog joins are environment-specific and left
   # to the calling skill to construct — this constant documents the
   # required OUTPUT SHAPE the parser below expects, not a runnable query.


def parse_introspection_rows(raw_text: str) -> dict:
    """Parses pipe-delimited rows of the form:
    table|column|type|is_nullable(YES/NO)|is_pk(YES/NO)|fk_table|fk_column
    (fk_table/fk_column empty when the column isn't a foreign key)."""
    entities_by_name = {}
    order = []
    relationships = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 7:
            continue  # malformed row, silently skip (introspection output, not user-facing SQL)
        table, column, sql_type, is_nullable, is_pk, fk_table, fk_column = parts
        if table not in entities_by_name:
            entities_by_name[table] = []
            order.append(table)
        field = {
            "name": column,
            "type": SQL_TYPE_TO_ABSTRACT.get(sql_type.upper(), "string"),
            "nullable": is_nullable.upper() == "YES",
        }
        if is_pk.upper() == "YES":
            field["pk"] = True
        entities_by_name[table].append(field)
        if fk_table:
            relationships.append({
                "from": table, "to": fk_table, "field": column,
                "cardinality": "many_to_one", "nullable": field["nullable"],
            })

    entities = [{"name": name, "fields": entities_by_name[name]} for name in order]
    return {"entities": entities, "relationships": relationships}


# ---------------------------------------------------------------------------
# Scale handling: connected components, then greedy BFS clustering
# ---------------------------------------------------------------------------


def _build_adjacency(entity_names, relationships):
    adj = {name: set() for name in entity_names}
    for rel in relationships:
        a, b = rel.get("from"), rel.get("to")
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    return adj


def connected_components(er: dict) -> list:
    entity_names = [e["name"] for e in er["entities"]]
    adj = _build_adjacency(entity_names, er["relationships"])
    seen = set()
    components = []
    for name in entity_names:
        if name in seen:
            continue
        stack = [name]
        component = set()
        while stack:
            n = stack.pop()
            if n in component:
                continue
            component.add(n)
            stack.extend(adj[n] - component)
        seen |= component
        components.append(component)
    return components


def cluster_large_component(entity_names, relationships, max_entities):
    """Greedy BFS clustering: seed from highest-degree node, grow to max_entities,
    repeat for remaining nodes. A disclosed heuristic, not real community detection."""
    adj = _build_adjacency(entity_names, relationships)
    remaining = set(entity_names)
    clusters = []
    while remaining:
        seed = max(remaining, key=lambda n: len(adj[n] & remaining))
        cluster = set()
        queue = [seed]
        while queue and len(cluster) < max_entities:
            n = queue.pop(0)
            if n in cluster or n not in remaining:
                continue
            cluster.add(n)
            queue.extend(sorted(adj[n] & remaining - cluster))
        remaining -= cluster
        clusters.append(cluster)
    return clusters


def build_diagrams(er: dict, max_entities: int = 40):
    """Returns list of (entity_name_set, relationships_subset) tuples, one per
    diagram, plus a disclosure dict describing whether clustering happened."""
    components = connected_components(er)
    all_names = [e["name"] for e in er["entities"]]
    final_clusters = []
    for component in components:
        if len(component) <= max_entities:
            final_clusters.append(component)
        else:
            final_clusters.extend(cluster_large_component(sorted(component), er["relationships"], max_entities))

    diagrams = []
    for cluster in final_clusters:
        rels = [r for r in er["relationships"] if r.get("from") in cluster and r.get("to") in cluster]
        diagrams.append((cluster, rels))

    disclosure = {
        "total_entities": len(all_names),
        "diagram_count": len(diagrams),
        "clustered": len(diagrams) > len(components),
        "components_found": len(components),
    }
    return diagrams, disclosure


# ---------------------------------------------------------------------------
# Mermaid rendering
# ---------------------------------------------------------------------------


def _mermaid_field_line(field: dict) -> str:
    mtype = MERMAID_TYPE_MAP.get(field["type"], "string")
    parts = [mtype, field["name"]]
    if field.get("pk"):
        parts.append("PK")
    if field.get("type") == "ref":
        parts.append("FK")
    line = " ".join(parts)
    if field.get("values"):
        comment = "enum: " + ", ".join(field["values"])
        line += f' "{comment}"'
    return f"  {line}"


def _relationship_symbol(rel: dict) -> str:
    if rel.get("cardinality") == "many_to_many":
        return "}o--o{"
    if rel.get("nullable", True):
        return "|o--o{"
    return "||--o{"


def render_mermaid(entity_names: set, relationships: list, er: dict) -> str:
    entities_by_name = {e["name"]: e for e in er["entities"]}
    lines = ["erDiagram"]

    for name in sorted(entity_names):
        entity = entities_by_name.get(name)
        if entity is None:
            continue
        field_lines = "\n".join(_mermaid_field_line(f) for f in entity["fields"])
        lines.append(f"  {name} {{\n{field_lines}\n  }}")

    for rel in relationships:
        symbol = _relationship_symbol(rel)
        label = rel.get("join_table") or rel.get("field") or "relates to"
        lines.append(f'  {rel["to"]} {symbol} {rel["from"]} : "{label}"')

    return "\n".join(lines) + "\n"


def render_mermaid_diagrams(er: dict, max_entities: int = 40):
    """Returns (list_of_mermaid_strings, disclosure_dict)."""
    diagrams, disclosure = build_diagrams(er, max_entities)
    rendered = [render_mermaid(entities, rels, er) for entities, rels in diagrams]
    return rendered, disclosure


# ---------------------------------------------------------------------------
# Mermaid structural validation (no external parser — our own invariants)
# ---------------------------------------------------------------------------


def validate_mermaid(text: str) -> list:
    errors = []
    # count only STRUCTURAL entity-block braces (a line that opens an entity
    # block, "Name {", vs. a line that's just "}") — naive whole-text {/}
    # counting is fooled by crow's-foot cardinality symbols like `||--o{`,
    # which contain a `{` that has nothing to do with entity-block nesting
    opens = len(re.findall(r"^\s*\w+\s*\{\s*$", text, re.MULTILINE))
    closes = len(re.findall(r"^\s*\}\s*$", text, re.MULTILINE))
    if opens != closes:
        errors.append("unbalanced braces")

    declared = set(re.findall(r"^\s*(\w+)\s*\{", text, re.MULTILINE))
    for match in re.finditer(r"^\s*(\w+)\s+(\S+)\s+(\w+)\s*:", text, re.MULTILINE):
        to_entity, symbol, from_entity = match.groups()
        if symbol not in VALID_CARDINALITY_SYMBOLS:
            errors.append(f"invalid cardinality symbol: {symbol!r}")
        if to_entity not in declared:
            errors.append(f"relationship references undeclared entity: {to_entity!r}")
        if from_entity not in declared:
            errors.append(f"relationship references undeclared entity: {from_entity!r}")
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="Render a lightweight ER representation into Mermaid")
    ap.add_argument("--er-file", required=True, help="Path to a lightweight ER JSON file")
    ap.add_argument("--max-entities", type=int, default=40)
    args = ap.parse_args()

    with open(args.er_file) as f:
        er = json.load(f)

    diagrams, disclosure = render_mermaid_diagrams(er, args.max_entities)
    all_errors = []
    for d in diagrams:
        all_errors.extend(validate_mermaid(d))

    print(json.dumps({"diagrams": diagrams, "disclosure": disclosure, "validation_errors": all_errors}, indent=2))


if __name__ == "__main__":
    main()
