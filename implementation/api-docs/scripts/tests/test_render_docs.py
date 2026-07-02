import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "design", "_shared"))

import render_docs  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


class TestRenderDocs(unittest.TestCase):
    def setUp(self):
        self.ir = load_fixture("bookmark_api.ir.json")

    def test_operation_headings_present(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("### `createBookmark`", out)
        self.assertIn("### `listBookmarks`", out)
        self.assertIn("### `deleteBookmark`", out)

    def test_rest_path_matches_shared_derivation(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("`POST /bookmarks`", out)
        self.assertIn("`GET /bookmarks`", out)
        self.assertIn("`DELETE /bookmarks/{id}`", out)

    def test_auth_and_scopes_rendered(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("**Auth required:** yes", out)
        self.assertIn("**Required scopes:** bookmarks:read", out)

    def test_pagination_rendered(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("**Paginated:** yes (cursor)", out)

    def test_request_field_table_rendered(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("| `postId` | ref(Post) | yes |", out)

    def test_error_table_rendered(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("| `not_found` |  | Post does not exist |", out)

    def test_description_placeholder_present_for_llm(self):
        out = render_docs.render_docs(self.ir)
        self.assertIn("<DESCRIPTION: expand on", out)
        self.assertIn("<EXAMPLE:request body>", out)

    def test_response_fields_empty_without_schema_ir(self):
        out = render_docs.render_docs(self.ir, schema_ir=None)
        self.assertIn("_No fields._", out)

    def test_response_fields_resolved_with_schema_ir(self):
        schema_ir = {
            "entities": [
                {"name": "Bookmark", "fields": [
                    {"name": "id", "type": "uuid", "nullable": False},
                    {"name": "user_id", "type": "ref", "ref_entity": "User", "nullable": False},
                ]}
            ]
        }
        out = render_docs.render_docs(self.ir, schema_ir=schema_ir)
        self.assertIn("| `user_id` | ref(User) | yes |", out)

    def test_no_entity_hint_flagged_low_confidence(self):
        ir = {
            "version": "1.0",
            "operations": [{
                "name": "healthCheck",
                "description": "Liveness probe.",
                "kind": "action",
                "input": {"fields": []},
                "output": {"cardinality": "single", "shape": {"fields": []}},
                "errors": [],
                "requires_auth": False,
                "required_scopes": [],
                "idempotent": True,
                "paginated": False,
                "pagination_style": None,
            }],
        }
        out = render_docs.render_docs(ir)
        self.assertIn("best guess", out)


if __name__ == "__main__":
    unittest.main()
