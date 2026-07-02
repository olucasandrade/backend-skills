"""
Unit tests for the deterministic layer of rfc-to-api (render_api.py).

Run with: python3 -m unittest discover -s tests -v
(from the scripts/ directory, stdlib unittest only — no deps)
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render_api  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def load_ir_pair():
    return load_fixture("blog_api_ir.json"), load_fixture("blog_schema_ir.json")


class TestValidation(unittest.TestCase):
    def test_valid_ir_has_no_errors(self):
        ir, schema_ir = load_ir_pair()
        self.assertEqual(render_api.validate_ir(ir, schema_ir), [])

    def test_unresolved_ref_without_schema_ir_detected(self):
        ir, _ = load_ir_pair()
        errors = render_api.validate_ir(ir, schema_ir=None)
        self.assertTrue(any("unresolved entity ref 'Post'" in e for e in errors))

    def test_duplicate_operation_name_detected(self):
        ir = {"operations": [
            {"name": "createPost", "kind": "create"},
            {"name": "createPost", "kind": "create"},
        ]}
        errors = render_api.validate_ir(ir)
        self.assertTrue(any("duplicate operation name" in e for e in errors))

    def test_unknown_kind_detected(self):
        ir = {"operations": [{"name": "doThing", "kind": "bogus"}]}
        errors = render_api.validate_ir(ir)
        self.assertTrue(any("unknown kind 'bogus'" in e for e in errors))

    def test_domain_specific_error_without_status_hint_detected(self):
        ir = {"operations": [
            {"name": "x", "kind": "action", "errors": [{"case": "insufficient_credits"}]}
        ]}
        errors = render_api.validate_ir(ir)
        self.assertTrue(any("missing a required status_hint" in e for e in errors))

    def test_base_vocabulary_error_without_status_hint_is_fine(self):
        ir = {"operations": [
            {"name": "x", "kind": "action", "errors": [{"case": "not_found"}]}
        ]}
        errors = render_api.validate_ir(ir)
        self.assertEqual(errors, [])

    def test_local_shapes_resolve_refs_when_no_schema_ir(self):
        ir = {
            "operations": [{
                "name": "getWidget", "kind": "read",
                "output": {"cardinality": "single", "shape": {"type": "ref", "ref_entity": "Widget"}},
            }],
            "shapes": [{"name": "Widget", "fields": [{"name": "id", "type": "uuid"}]}],
        }
        self.assertEqual(render_api.validate_ir(ir), [])


class TestPathVerbDerivation(unittest.TestCase):
    def setUp(self):
        self.ir, _ = load_ir_pair()
        self.ops = {op["name"]: op for op in self.ir["operations"]}

    def test_create_maps_to_post_collection(self):
        path, verb, confident = render_api.derive_rest_path_verb(self.ops["createPost"])
        self.assertEqual((path, verb), ("/posts", "POST"))
        self.assertTrue(confident)

    def test_list_maps_to_get_collection(self):
        path, verb, _ = render_api.derive_rest_path_verb(self.ops["listPosts"])
        self.assertEqual((path, verb), ("/posts", "GET"))

    def test_read_maps_to_get_item(self):
        path, verb, _ = render_api.derive_rest_path_verb(self.ops["getPost"])
        self.assertEqual((path, verb), ("/posts/{id}", "GET"))

    def test_delete_maps_to_delete_item(self):
        path, verb, _ = render_api.derive_rest_path_verb(self.ops["deletePost"])
        self.assertEqual((path, verb), ("/posts/{id}", "DELETE"))

    def test_action_maps_to_subpath(self):
        path, verb, confident = render_api.derive_rest_path_verb(self.ops["publishPost"])
        self.assertEqual((path, verb), ("/posts/{id}/publish", "POST"))
        self.assertFalse(confident)  # derived, not stated

    def test_explicit_override_used_verbatim(self):
        path, verb, confident = render_api.derive_rest_path_verb(self.ops["archiveOldPosts"])
        self.assertEqual((path, verb), ("/admin/posts/archive-old", "POST"))
        self.assertTrue(confident)  # explicit, not derived

    def test_flat_fallback_when_no_entity_and_no_override(self):
        op = {"name": "pingServer", "kind": "action", "input": {"fields": []}, "output": {}}
        path, verb, confident = render_api.derive_rest_path_verb(op)
        self.assertEqual(path, "/pingServer")
        self.assertFalse(confident)


class TestTransitiveEntityReferences(unittest.TestCase):
    """Regression: an entity reachable only THROUGH another referenced
    entity's own ref field (not directly mentioned by any operation) must
    still be declared — caught during a live pipeline dry-run where
    `Bookmark.user_id: ref->User` produced a `$ref`/type reference to
    `User` in the output even though no operation input/output ever
    mentions User directly."""

    def setUp(self):
        self.schema_ir = {
            "entities": [
                {"name": "User", "fields": [{"name": "id", "type": "uuid", "nullable": False}]},
                {"name": "Post", "fields": [{"name": "id", "type": "uuid", "nullable": False}]},
                {"name": "Bookmark", "fields": [
                    {"name": "id", "type": "uuid", "nullable": False},
                    {"name": "userId", "type": "ref", "ref_entity": "User", "nullable": False},
                    {"name": "postId", "type": "ref", "ref_entity": "Post", "nullable": False},
                ]},
            ]
        }
        self.ir = {"operations": [{
            "name": "getBookmark", "kind": "read", "entity": "Bookmark",
            "input": {"fields": []},
            "output": {"cardinality": "single", "shape": {"type": "ref", "ref_entity": "Bookmark"}},
            "errors": [], "requires_auth": False, "required_scopes": [],
        }]}

    def test_collect_referenced_entities_includes_transitive_refs(self):
        referenced = render_api.collect_referenced_entities(self.ir, self.schema_ir, [])
        self.assertEqual(referenced, {"Bookmark", "User", "Post"})

    def test_openapi_declares_transitively_referenced_schema(self):
        spec = render_api.render_openapi(self.ir, self.schema_ir)
        self.assertIn("User", spec["components"]["schemas"])

    def test_openapi_no_dangling_schema_refs(self):
        spec = render_api.render_openapi(self.ir, self.schema_ir)
        declared = set(spec["components"]["schemas"].keys())
        raw = json.dumps(spec)
        for ref_name in re.findall(r'#/components/schemas/(\w+)', raw):
            self.assertIn(ref_name, declared, f"dangling $ref to undeclared schema '{ref_name}'")

    def test_graphql_declares_transitively_referenced_type(self):
        sdl = render_api.render_graphql(self.ir, self.schema_ir)
        self.assertIn("type User {", sdl)

    def test_graphql_no_dangling_type_refs(self):
        sdl = render_api.render_graphql(self.ir, self.schema_ir)
        declared = set(re.findall(r"^type (\w+) \{", sdl, re.MULTILINE))
        for entity_name in ("User", "Post", "Bookmark"):
            self.assertIn(entity_name, declared)


class TestOpenApiRendering(unittest.TestCase):
    def setUp(self):
        self.ir, self.schema_ir = load_ir_pair()
        self.spec = render_api.render_openapi(self.ir, self.schema_ir)

    def test_top_level_required_keys_present(self):
        for key in ("openapi", "info", "paths", "components"):
            self.assertIn(key, self.spec)

    def test_every_path_item_has_valid_method_keys(self):
        valid_methods = {"get", "post", "put", "patch", "delete"}
        for path, item in self.spec["paths"].items():
            for method in item:
                self.assertIn(method, valid_methods, f"invalid method '{method}' on {path}")

    def test_every_response_has_status_code_keys(self):
        for path, item in self.spec["paths"].items():
            for method, op in item.items():
                for status in op["responses"]:
                    self.assertTrue(status.isdigit() or status == "default", f"bad status key: {status}")

    def test_referenced_entity_schema_present(self):
        self.assertIn("Post", self.spec["components"]["schemas"])
        self.assertIn("title", self.spec["components"]["schemas"]["Post"]["properties"])

    def test_create_operation_has_request_body(self):
        op = self.spec["paths"]["/posts"]["post"]
        self.assertIn("requestBody", op)

    def test_list_operation_has_no_request_body(self):
        op = self.spec["paths"]["/posts"]["get"]
        self.assertNotIn("requestBody", op)

    def test_pagination_adds_cursor_and_limit_query_params(self):
        op = self.spec["paths"]["/posts"]["get"]
        param_names = {p["name"] for p in op.get("parameters", [])}
        self.assertIn("cursor", param_names)
        self.assertIn("limit", param_names)

    def test_id_path_param_added_for_item_paths(self):
        op = self.spec["paths"]["/posts/{id}"]["get"]
        param_names = {p["name"] for p in op.get("parameters", [])}
        self.assertIn("id", param_names)

    def test_delete_returns_204(self):
        op = self.spec["paths"]["/posts/{id}"]["delete"]
        self.assertIn("204", op["responses"])

    def test_create_returns_201(self):
        op = self.spec["paths"]["/posts"]["post"]
        self.assertIn("201", op["responses"])

    def test_domain_specific_error_status_mapped(self):
        op = self.spec["paths"]["/posts/{id}/publish"]["post"]
        self.assertIn("402", op["responses"])

    def test_base_vocabulary_error_status_mapped(self):
        op = self.spec["paths"]["/posts/{id}"]["get"]
        self.assertIn("404", op["responses"])

    def test_auth_required_adds_security_and_scopes(self):
        op = self.spec["paths"]["/posts"]["post"]
        self.assertIn("security", op)
        self.assertEqual(op["x-required-scopes"], ["posts:write"])

    def test_security_scheme_declared_when_needed(self):
        self.assertIn("bearerAuth", self.spec["components"]["securitySchemes"])

    def test_low_confidence_derivation_flagged(self):
        op = self.spec["paths"]["/posts/{id}/publish"]["post"]
        self.assertEqual(op.get("x-path-derivation-confidence"), "low")

    def test_output_is_json_serializable(self):
        raw = json.dumps(self.spec)
        json.loads(raw)  # no exception


class TestGraphqlRendering(unittest.TestCase):
    def setUp(self):
        self.ir, self.schema_ir = load_ir_pair()
        self.sdl = render_api.render_graphql(self.ir, self.schema_ir)

    def test_entity_type_declared(self):
        self.assertIn("type Post {", self.sdl)

    def test_query_and_mutation_types_present(self):
        self.assertIn("type Query {", self.sdl)
        self.assertIn("type Mutation {", self.sdl)

    def test_list_operation_is_a_query_field(self):
        query_block = self.sdl.split("type Query {")[1].split("}")[0]
        self.assertIn("listPosts", query_block)

    def test_create_operation_is_a_mutation_field(self):
        mutation_block = self.sdl.split("type Mutation {")[1].split("}")[0]
        self.assertIn("createPost", mutation_block)

    def test_cursor_pagination_generates_connection_types(self):
        self.assertIn("type PostConnection {", self.sdl)
        self.assertIn("type PostEdge {", self.sdl)
        self.assertIn("pageInfo: PageInfo!", self.sdl)

    def test_input_type_generated_for_create(self):
        self.assertIn("input CreatePostInput {", self.sdl)

    def test_ref_field_in_input_becomes_id(self):
        input_block = self.sdl.split("input CreatePostInput {")[1].split("}")[0]
        self.assertIn("authorId: ID!", input_block)

    def test_operation_with_errors_gets_payload_type(self):
        self.assertIn("Payload {", self.sdl)
        self.assertIn("errors: [Error!]", self.sdl)

    def test_datetime_custom_scalar_declared_when_used(self):
        self.assertIn("scalar DateTime", self.sdl)

    def test_every_brace_balanced(self):
        self.assertEqual(self.sdl.count("{"), self.sdl.count("}"))

    def test_output_is_deterministic(self):
        sdl2 = render_api.render_graphql(self.ir, self.schema_ir)
        self.assertEqual(self.sdl, sdl2)

    def test_enum_field_type_is_declared_not_dangling(self):
        # regression: a field typed `role: RoleEnum!` is invalid SDL unless
        # `enum RoleEnum { ... }` is actually declared somewhere in the doc
        self.assertIn("role: UserRoleEnum!", self.sdl)
        self.assertIn("enum UserRoleEnum {", self.sdl)
        self.assertIn("ADMIN", self.sdl)
        self.assertIn("MEMBER", self.sdl)

    def test_entity_field_names_are_camelcase_not_snake_case(self):
        # regression: schema-IR field names (author_id, created_at) are
        # snake_case by DB convention; GraphQL idiom expects camelCase
        self.assertIn("authorId: User!", self.sdl)
        self.assertIn("createdAt: DateTime!", self.sdl)
        self.assertNotIn("author_id", self.sdl)
        self.assertNotIn("created_at", self.sdl)

    def test_inline_output_shape_gets_named_type_not_bare_json(self):
        # regression: an operation whose output is a locally-defined object
        # (not a $ref to an entity) used to collapse to a bare `JSON` scalar,
        # discarding real structure
        self.assertIn("type ArchiveOldPostsResult {", self.sdl)
        self.assertIn("archivedCount: Int!", self.sdl)
        self.assertIn("archiveOldPosts: ArchiveOldPostsResult", self.sdl)

    def test_empty_output_shape_uses_generic_data_field_not_mangled_name(self):
        # regression: a truly-empty output (delete) used to fall back to
        # bare "JSON" and then mangle it into a field named "jSON"
        self.assertIn("data: JSON", self.sdl)
        self.assertNotIn("jSON", self.sdl)


class TestAssumedFlagPropagation(unittest.TestCase):
    def test_assumed_field_flagged_in_openapi(self):
        ir = {"operations": [{
            "name": "createWidget", "kind": "create",
            "input": {"fields": [{"name": "id", "type": "uuid", "nullable": False, "assumed": True, "assumed_reason": "inferred pk"}]},
            "output": {"cardinality": "single", "shape": {"fields": []}},
            "errors": [], "requires_auth": False, "required_scopes": [],
        }]}
        spec = render_api.render_openapi(ir, schema_ir=None)
        id_schema = spec["paths"]["/createWidget"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["id"]
        self.assertTrue(id_schema["x-assumed"])


if __name__ == "__main__":
    unittest.main()
