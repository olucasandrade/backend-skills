"""
Unit tests for the deterministic layer of er-generator (render_er.py).

Run with: python3 -m unittest discover -s tests -v
(from the scripts/ directory, stdlib unittest only — no deps)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render_er  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    path = os.path.join(FIXTURES, name)
    if name.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    with open(path) as f:
        return f.read()


class TestProjectSchemaIr(unittest.TestCase):
    def setUp(self):
        self.er = render_er.project_schema_ir(load_fixture("blog_schema_ir.json"))

    def test_all_entities_present(self):
        names = {e["name"] for e in self.er["entities"]}
        self.assertEqual(names, {"User", "Post", "Tag"})

    def test_ref_field_becomes_relationship(self):
        rels = [r for r in self.er["relationships"] if r.get("field") == "author_id"]
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0], {
            "from": "Post", "to": "User", "field": "author_id",
            "cardinality": "many_to_one", "nullable": False,
        })

    def test_many_to_many_relationship_preserved(self):
        m2m = [r for r in self.er["relationships"] if r["cardinality"] == "many_to_many"]
        self.assertEqual(len(m2m), 1)
        self.assertEqual(m2m[0]["join_table"], "post_tags")

    def test_enum_values_carried_over(self):
        user = next(e for e in self.er["entities"] if e["name"] == "User")
        role_field = next(f for f in user["fields"] if f["name"] == "role")
        self.assertEqual(role_field["values"], ["admin", "member"])

    def test_primary_key_flag_carried_over(self):
        user = next(e for e in self.er["entities"] if e["name"] == "User")
        id_field = next(f for f in user["fields"] if f["name"] == "id")
        self.assertTrue(id_field["pk"])


class TestSqliteIntrospection(unittest.TestCase):
    def setUp(self):
        self.er = render_er.parse_sqlite_file(os.path.join(FIXTURES, "blog.sqlite"))

    def test_tables_discovered(self):
        names = {e["name"] for e in self.er["entities"]}
        self.assertEqual(names, {"users", "posts"})

    def test_column_types_mapped(self):
        posts = next(e for e in self.er["entities"] if e["name"] == "posts")
        title = next(f for f in posts["fields"] if f["name"] == "title")
        self.assertEqual(title["type"], "string")

    def test_primary_key_detected(self):
        users = next(e for e in self.er["entities"] if e["name"] == "users")
        id_field = next(f for f in users["fields"] if f["name"] == "id")
        self.assertTrue(id_field["pk"])

    def test_foreign_key_detected_as_relationship(self):
        rels = [r for r in self.er["relationships"] if r["from"] == "posts"]
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["to"], "users")
        self.assertEqual(rels[0]["field"], "author_id")

    def test_nullable_column_detected(self):
        users = next(e for e in self.er["entities"] if e["name"] == "users")
        age = next(f for f in users["fields"] if f["name"] == "age")
        self.assertTrue(age["nullable"])
        email = next(f for f in users["fields"] if f["name"] == "email")
        self.assertFalse(email["nullable"])


class TestStaticSqlParsing(unittest.TestCase):
    def setUp(self):
        self.sql = load_fixture("blog_schema.sql")
        self.er, self.report = render_er.parse_create_table_sql(self.sql)

    def test_all_three_tables_appear_as_entities(self):
        names = {e["name"] for e in self.er["entities"]}
        self.assertEqual(names, {"users", "posts", "weird_table"})

    def test_users_and_posts_parsed_successfully(self):
        self.assertIn("users", self.report["parsed"])
        self.assertIn("posts", self.report["parsed"])

    def test_weird_table_reported_as_skipped_not_silently_wrong(self):
        self.assertNotIn("weird_table", self.report["parsed"])
        reasons = [s["reason"] for s in self.report["skipped"]]
        self.assertTrue(any("CUSTOMTYPE" in r for r in reasons))

    def test_weird_table_still_gets_an_entity_entry_with_partial_fields(self):
        # the recognized `id` column should still show up even though the
        # table overall wasn't fully parsed — no silent full-table drop
        weird = next(e for e in self.er["entities"] if e["name"] == "weird_table")
        field_names = {f["name"] for f in weird["fields"]}
        self.assertIn("id", field_names)

    def test_table_level_constraint_line_does_not_produce_a_skip(self):
        # CONSTRAINT ... CHECK(...) is a table-level constraint, not an
        # unparseable column — must not be reported as a parse failure
        reasons = [s["reason"] for s in self.report["skipped"]]
        self.assertFalse(any("chk_posts_something" in r for r in reasons))

    def test_foreign_key_reference_detected(self):
        rels = [r for r in self.er["relationships"] if r["from"] == "posts"]
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["to"], "users")

    def test_not_null_reflected(self):
        posts = next(e for e in self.er["entities"] if e["name"] == "posts")
        title = next(f for f in posts["fields"] if f["name"] == "title")
        self.assertFalse(title["nullable"])


class TestIntrospectionRowParsing(unittest.TestCase):
    def setUp(self):
        self.raw = load_fixture("introspection_rows.txt")
        self.er = render_er.parse_introspection_rows(self.raw)

    def test_tables_grouped_correctly(self):
        names = {e["name"] for e in self.er["entities"]}
        self.assertEqual(names, {"users", "posts"})

    def test_column_order_preserved_within_table(self):
        posts = next(e for e in self.er["entities"] if e["name"] == "posts")
        field_names = [f["name"] for f in posts["fields"]]
        self.assertEqual(field_names, ["id", "title", "author_id"])

    def test_foreign_key_column_becomes_relationship(self):
        self.assertEqual(len(self.er["relationships"]), 1)
        rel = self.er["relationships"][0]
        self.assertEqual((rel["from"], rel["to"], rel["field"]), ("posts", "users", "author_id"))

    def test_pk_flag_parsed(self):
        users = next(e for e in self.er["entities"] if e["name"] == "users")
        id_field = next(f for f in users["fields"] if f["name"] == "id")
        self.assertTrue(id_field["pk"])

    def test_malformed_row_silently_skipped_not_crashed(self):
        raw = self.raw + "\nthis|is|not|a|valid|row\n"  # 6 fields, not 7
        er = render_er.parse_introspection_rows(raw)
        names = {e["name"] for e in er["entities"]}
        self.assertEqual(names, {"users", "posts"})  # no crash, no phantom entity


class TestConnectedComponents(unittest.TestCase):
    def test_single_component_when_all_linked(self):
        er = render_er.project_schema_ir(load_fixture("blog_schema_ir.json"))
        components = render_er.connected_components(er)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0], {"User", "Post", "Tag"})

    def test_two_components_when_disconnected(self):
        er = {
            "entities": [{"name": "A", "fields": []}, {"name": "B", "fields": []},
                         {"name": "C", "fields": []}, {"name": "D", "fields": []}],
            "relationships": [{"from": "A", "to": "B", "cardinality": "many_to_one"}],
        }
        components = render_er.connected_components(er)
        self.assertEqual(len(components), 3)  # {A,B}, {C}, {D}


class TestClustering(unittest.TestCase):
    def test_cluster_large_component_respects_max_size(self):
        names = [f"E{i}" for i in range(10)]
        relationships = [{"from": names[i], "to": names[i + 1], "cardinality": "many_to_one"} for i in range(9)]
        clusters = render_er.cluster_large_component(names, relationships, max_entities=4)
        for c in clusters:
            self.assertLessEqual(len(c), 4)

    def test_cluster_large_component_covers_all_entities(self):
        names = [f"E{i}" for i in range(10)]
        relationships = [{"from": names[i], "to": names[i + 1], "cardinality": "many_to_one"} for i in range(9)]
        clusters = render_er.cluster_large_component(names, relationships, max_entities=4)
        covered = set()
        for c in clusters:
            covered |= c
        self.assertEqual(covered, set(names))

    def test_build_diagrams_no_clustering_when_under_cap(self):
        er = render_er.project_schema_ir(load_fixture("blog_schema_ir.json"))
        diagrams, disclosure = render_er.build_diagrams(er, max_entities=40)
        self.assertEqual(len(diagrams), 1)
        self.assertFalse(disclosure["clustered"])

    def test_build_diagrams_clusters_when_over_cap(self):
        names = [f"E{i}" for i in range(10)]
        relationships = [{"from": names[i], "to": names[i + 1], "cardinality": "many_to_one"} for i in range(9)]
        er = {"entities": [{"name": n, "fields": []} for n in names], "relationships": relationships}
        diagrams, disclosure = render_er.build_diagrams(er, max_entities=4)
        self.assertGreater(len(diagrams), 1)
        self.assertTrue(disclosure["clustered"])
        self.assertEqual(disclosure["total_entities"], 10)


class TestMermaidRendering(unittest.TestCase):
    def setUp(self):
        self.er = render_er.project_schema_ir(load_fixture("blog_schema_ir.json"))
        diagrams, self.disclosure = render_er.render_mermaid_diagrams(self.er, max_entities=40)
        self.assertEqual(len(diagrams), 1)
        self.sdl = diagrams[0]

    def test_starts_with_er_diagram_keyword(self):
        self.assertTrue(self.sdl.startswith("erDiagram"))

    def test_all_entities_declared(self):
        for name in ("User", "Post", "Tag"):
            self.assertIn(f"{name} {{", self.sdl)

    def test_pk_marker_present(self):
        self.assertIn("PK", self.sdl)

    def test_enum_rendered_as_string_with_comment(self):
        self.assertIn('string role "enum: admin, member"', self.sdl)

    def test_required_fk_uses_solid_one_symbol(self):
        # author_id is NOT NULL -> "one" side should be solid (||), not optional (|o)
        self.assertIn("User ||--o{ Post", self.sdl)

    def test_many_to_many_uses_open_both_ends_symbol(self):
        self.assertIn("}o--o{", self.sdl)

    def test_relationship_label_present(self):
        self.assertIn('"author_id"', self.sdl)

    def test_fk_field_typed_as_uuid_not_generic_string(self):
        # regression: a `ref`-typed field fell through MERMAID_TYPE_MAP's
        # default and silently rendered as generic "string", misrepresenting
        # a foreign key column
        self.assertIn("uuid author_id FK", self.sdl)
        self.assertNotIn("string author_id", self.sdl)

    def test_output_passes_own_validation(self):
        errors = render_er.validate_mermaid(self.sdl)
        self.assertEqual(errors, [])

    def test_output_is_deterministic(self):
        diagrams2, _ = render_er.render_mermaid_diagrams(self.er, max_entities=40)
        self.assertEqual(self.sdl, diagrams2[0])


class TestMermaidValidation(unittest.TestCase):
    def test_unbalanced_braces_detected(self):
        errors = render_er.validate_mermaid("erDiagram\n  User {\n  id uuid PK\n")
        self.assertIn("unbalanced braces", errors)

    def test_dangling_relationship_reference_detected(self):
        text = 'erDiagram\n  User {\n  id uuid PK\n  }\n  User ||--o{ Ghost : "x"\n'
        errors = render_er.validate_mermaid(text)
        self.assertTrue(any("Ghost" in e for e in errors))

    def test_invalid_cardinality_symbol_detected(self):
        text = 'erDiagram\n  User {\n  id uuid PK\n  }\n  Post {\n  id uuid PK\n  }\n  User ??--?? Post : "x"\n'
        errors = render_er.validate_mermaid(text)
        self.assertTrue(any("invalid cardinality symbol" in e for e in errors))

    def test_valid_diagram_has_no_errors(self):
        text = 'erDiagram\n  User {\n  uuid id PK\n  }\n  Post {\n  uuid id PK\n  }\n  User ||--o{ Post : "author_id"\n'
        self.assertEqual(render_er.validate_mermaid(text), [])


if __name__ == "__main__":
    unittest.main()
