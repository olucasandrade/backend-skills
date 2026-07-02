"""
Unit tests for the deterministic layer of rfc-to-schema (render_schema.py).

Run with: python3 -m unittest discover -s tests -v
(from the scripts/ directory, stdlib unittest only — no deps)
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render_schema  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


class TestValidation(unittest.TestCase):
    def test_valid_ir_has_no_errors(self):
        ir = load_fixture("blog_ir.json")
        self.assertEqual(render_schema.validate_ir(ir), [])

    def test_duplicate_field_name_detected(self):
        ir = load_fixture("invalid_ir.json")
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("duplicate field name 'id'" in e for e in errors))

    def test_dangling_ref_detected(self):
        ir = load_fixture("invalid_ir.json")
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("unknown entity 'Nonexistent'" in e for e in errors))

    def test_enum_without_values_detected(self):
        ir = load_fixture("invalid_ir.json")
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("enum field has no 'values'" in e for e in errors))

    def test_unique_constraint_referencing_unknown_field_detected(self):
        ir = {"entities": [{"name": "X", "fields": [{"name": "a", "type": "uuid"}],
                             "unique_constraints": [["a", "ghost"]]}]}
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("unknown field 'ghost'" in e for e in errors))

    def test_unique_constraint_with_single_field_detected(self):
        ir = {"entities": [{"name": "X", "fields": [{"name": "a", "type": "uuid"}],
                             "unique_constraints": [["a"]]}]}
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("needs at least 2 fields" in e for e in errors))

    def test_unknown_type_detected(self):
        ir = {"entities": [{"name": "X", "fields": [{"name": "f", "type": "bogus"}]}]}
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("unknown type 'bogus'" in e for e in errors))

    def test_relationship_to_unknown_entity_detected(self):
        ir = {
            "entities": [{"name": "A", "fields": [{"name": "id", "type": "uuid"}]}],
            "relationships": [{"between": ["A", "Ghost"]}],
        }
        errors = render_schema.validate_ir(ir)
        self.assertTrue(any("unknown entity: Ghost" in e for e in errors))


class TestNaming(unittest.TestCase):
    def test_slugify_pascal_case(self):
        self.assertEqual(render_schema.slugify_table_name("BlogPost"), "blog_posts")

    def test_slugify_already_plural_like(self):
        self.assertEqual(render_schema.slugify_table_name("News"), "news")

    def test_table_name_override_respected(self):
        entity = {"name": "User", "table_name": "app_users"}
        self.assertEqual(render_schema.table_name_for(entity), "app_users")

    def test_table_name_defaults_to_slug(self):
        entity = {"name": "Tag"}
        self.assertEqual(render_schema.table_name_for(entity), "tags")


class TestSqlRendering(unittest.TestCase):
    def setUp(self):
        self.ir = load_fixture("blog_ir.json")
        self.sql = render_schema.render_sql(self.ir)

    def test_creates_all_tables(self):
        self.assertIn("CREATE TABLE users (", self.sql)
        self.assertIn("CREATE TABLE posts (", self.sql)
        self.assertIn("CREATE TABLE tags (", self.sql)

    def test_primary_key_rendered(self):
        self.assertIn("id UUID PRIMARY KEY", self.sql)

    def test_varchar_with_length(self):
        self.assertIn("email VARCHAR(255)", self.sql)

    def test_not_null_on_required_field(self):
        self.assertIn("title VARCHAR(200) NOT NULL", self.sql)

    def test_unique_constraint(self):
        self.assertIn("email VARCHAR(255) NOT NULL UNIQUE", self.sql)

    def test_enum_becomes_text_with_check_constraint(self):
        self.assertIn("role TEXT NOT NULL", self.sql)
        self.assertIn("CHECK (role IN ('admin', 'member'))", self.sql)

    def test_ref_field_becomes_uuid_fk(self):
        self.assertIn("author_id UUID NOT NULL REFERENCES users(id)", self.sql)

    def test_array_of_scalars_becomes_native_array(self):
        self.assertIn("tags VARCHAR[]", self.sql)

    def test_object_field_becomes_jsonb(self):
        self.assertIn("metadata JSONB", self.sql)

    def test_assumed_field_has_comment(self):
        self.assertIn("-- ASSUMED: standard primary key convention", self.sql)

    def test_non_assumed_field_has_no_comment(self):
        for line in self.sql.splitlines():
            if line.strip().startswith("email "):
                self.assertNotIn("ASSUMED", line)

    def test_many_to_many_join_table_generated(self):
        self.assertIn("CREATE TABLE post_tags (", self.sql)
        self.assertIn("PRIMARY KEY (post_id, tag_id)", self.sql)

    def test_composite_unique_constraint_rendered(self):
        self.assertIn("CONSTRAINT uq_posts_title_author_id UNIQUE (title, author_id)", self.sql)

    def test_output_is_deterministic(self):
        sql2 = render_schema.render_sql(self.ir)
        self.assertEqual(self.sql, sql2)

    def test_no_comma_swallowed_by_trailing_comment(self):
        # regression: a `-- ASSUMED` comment placed before the column's
        # trailing comma silently eats the comma (SQL comments run to EOL),
        # merging two columns into invalid syntax. Every non-last line
        # inside a CREATE TABLE body must end with a real comma that is
        # NOT inside a `--` comment.
        for block in self.sql.split("CREATE TABLE ")[1:]:
            body = block.split("(", 1)[1].rsplit(");", 1)[0]
            lines = [l for l in body.splitlines() if l.strip()]
            for line in lines[:-1]:
                stripped = line.rstrip()
                if "--" in stripped:
                    code_part, _, comment_part = stripped.partition("--")
                    self.assertTrue(
                        code_part.rstrip().endswith(","),
                        f"comma swallowed by comment in line: {line!r}",
                    )
                else:
                    self.assertTrue(stripped.endswith(","), f"missing trailing comma: {line!r}")


class TestJsonSchemaRendering(unittest.TestCase):
    def setUp(self):
        self.ir = load_fixture("blog_ir.json")
        self.schema = render_schema.render_json_schema(self.ir)

    def test_defs_created_for_each_entity(self):
        self.assertIn("User", self.schema["$defs"])
        self.assertIn("Post", self.schema["$defs"])
        self.assertIn("Tag", self.schema["$defs"])

    def test_composite_unique_constraint_carried_as_extension(self):
        self.assertEqual(self.schema["$defs"]["Post"]["x-unique-constraints"], [["title", "author_id"]])

    def test_no_extension_key_when_no_constraints_declared(self):
        self.assertNotIn("x-unique-constraints", self.schema["$defs"]["User"])

    def test_required_fields_reflect_nullability(self):
        user_required = self.schema["$defs"]["User"]["required"]
        self.assertIn("id", user_required)     # nullable: false in fixture
        self.assertIn("email", user_required)  # nullable: false in fixture
        post_required = self.schema["$defs"]["Post"]["required"]
        self.assertNotIn("metadata", post_required)  # nullable: true in fixture

    def test_enum_field_has_enum_values(self):
        role_prop = self.schema["$defs"]["User"]["properties"]["role"]
        self.assertEqual(role_prop["enum"], ["admin", "member"])

    def test_ref_field_becomes_json_ref(self):
        author_prop = self.schema["$defs"]["Post"]["properties"]["author_id"]
        self.assertEqual(author_prop["$ref"], "#/$defs/User")

    def test_array_of_scalars_rendered(self):
        tags_prop = self.schema["$defs"]["Post"]["properties"]["tags"]
        self.assertEqual(tags_prop["type"], "array")
        self.assertEqual(tags_prop["items"], {"type": "string"})

    def test_nested_object_field_rendered_with_properties(self):
        metadata_prop = self.schema["$defs"]["Post"]["properties"]["metadata"]
        self.assertEqual(metadata_prop["type"], "object")
        self.assertIn("source", metadata_prop["properties"])

    def test_assumed_field_flagged(self):
        id_prop = self.schema["$defs"]["User"]["properties"]["id"]
        self.assertTrue(id_prop["x-assumed"])
        self.assertIn("standard primary key convention", id_prop["x-assumed-reason"])

    def test_non_assumed_field_not_flagged(self):
        email_prop = self.schema["$defs"]["User"]["properties"]["email"]
        self.assertNotIn("x-assumed", email_prop)

    def test_output_is_valid_json_serializable(self):
        # round-trips through json.dumps/loads without error
        raw = json.dumps(self.schema)
        reloaded = json.loads(raw)
        self.assertEqual(reloaded["$defs"]["User"]["properties"]["email"]["type"], "string")


class TestCliValidationFailure(unittest.TestCase):
    def test_invalid_ir_reports_errors_not_partial_output(self):
        ir = load_fixture("invalid_ir.json")
        errors = render_schema.validate_ir(ir)
        self.assertGreater(len(errors), 0)
        # rendering should not even be attempted by the CLI when invalid;
        # this is enforced in main(), asserted here at the validate_ir level
        # since main() is a thin CLI wrapper.


if __name__ == "__main__":
    unittest.main()
