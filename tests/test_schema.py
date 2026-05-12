import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.schema import validate_suite


class SchemaTest(unittest.TestCase):
    def test_allows_params_and_setup_expect(self):
        suite = {
            "metadata": {"api": "GET /items"},
            "setup": [
                {
                    "id": "create_item",
                    "action": "http",
                    "request": {
                        "method": "POST",
                        "url": "http://example.com/items",
                        "params": {"source": "test"},
                    },
                    "expect": {"status": 201, "body": {"data.id": "@notNull"}},
                    "extract": {"itemId": "$.data.id"},
                }
            ],
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常查询",
                    "dimension": "functional_positive",
                    "priority": "P0",
                    "source": "app.py:10",
                    "request": {
                        "method": "GET",
                        "url": "http://example.com/items",
                        "query": {"id": "{{itemId}}"},
                    },
                    "expect": {"status": 200},
                }
            ],
        }

        self.assertEqual([], validate_suite(suite))

    def test_rejects_params_and_query_together(self):
        suite = {
            "metadata": {"api": "GET /items"},
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常查询",
                    "dimension": "functional_positive",
                    "priority": "P0",
                    "source": "app.py:10",
                    "request": {
                        "method": "GET",
                        "url": "http://example.com/items",
                        "params": {"a": "1"},
                        "query": {"b": "2"},
                    },
                    "expect": {"status": 200},
                }
            ],
        }

        errors = validate_suite(suite)
        self.assertTrue(any("must not include both params and query" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
