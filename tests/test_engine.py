import sys
import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.engine import TestEngine
from ai_api_tester.report import ReportGenerator


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _call(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self._call("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("DELETE", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._call("PATCH", url, **kwargs)

    def request(self, method, url, **kwargs):
        return self._call(method, url, **kwargs)


class EngineTest(unittest.TestCase):
    def test_setup_expect_params_extract_case_and_teardown(self):
        engine = TestEngine()
        engine.session = FakeSession([
            FakeResponse(201, {"data": {"id": 42}}),
            FakeResponse(200, {"data": {"id": 42, "name": "item"}}, {"X-Trace": "abc"}),
            FakeResponse(204, {}),
        ])

        suite = {
            "metadata": {"api": "GET /items", "dimensions_covered": ["functional_positive"]},
            "env": {"base_url": "http://example.com"},
            "setup": [
                {
                    "id": "create_item",
                    "request": {
                        "method": "POST",
                        "url": "{{env.base_url}}/items",
                        "params": {"source": "setup"},
                        "body": {"name": "item"},
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
                        "url": "{{env.base_url}}/items",
                        "query": {"id": "{{itemId}}"},
                    },
                    "expect": {
                        "status": 200,
                        "headers": {"X-Trace": "@notNull"},
                        "body": {"data.id": 42},
                    },
                    "extract": {"resultId": "$.data.id"},
                    "teardown": [
                        {
                            "request": {
                                "method": "DELETE",
                                "url": "{{env.base_url}}/items/{{resultId}}",
                                "params": {"reason": "cleanup"},
                            }
                        }
                    ],
                }
            ],
        }

        result = engine.run_suite(suite)

        self.assertEqual(1, result.total)
        self.assertEqual(1, result.passed)
        self.assertEqual("pass", result.cases[0].status)
        self.assertEqual({"resultId": 42}, result.cases[0].extracted_variables)
        self.assertEqual({"id": "42"}, engine.session.calls[1]["params"])
        self.assertEqual("http://example.com/items/42", engine.session.calls[2]["url"])
        self.assertEqual({"reason": "cleanup"}, engine.session.calls[2]["params"])

        report = json.loads(ReportGenerator().json_report(result))
        case_report = report["cases"][0]
        self.assertEqual({"id": "42"}, case_report["request"]["params"])
        self.assertEqual({"X-Trace": "abc"}, case_report["response_headers"])
        self.assertEqual({"resultId": 42}, case_report["extracted_variables"])

    def test_setup_expect_failure_stops_cases(self):
        engine = TestEngine()
        engine.session = FakeSession([
            FakeResponse(500, {"error": "setup failed"}),
        ])
        suite = {
            "metadata": {"api": "GET /items"},
            "setup": [
                {
                    "id": "setup",
                    "request": {"method": "GET", "url": "http://example.com/setup"},
                    "expect": {"status": 200},
                }
            ],
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常查询",
                    "dimension": "functional_positive",
                    "priority": "P0",
                    "source": "app.py:10",
                    "request": {"method": "GET", "url": "http://example.com/items"},
                    "expect": {"status": 200},
                }
            ],
        }

        result = engine.run_suite(suite)

        self.assertEqual(1, result.total)
        self.assertEqual(1, result.errored)
        self.assertEqual([], result.cases)
        self.assertEqual(1, len(engine.session.calls))


if __name__ == "__main__":
    unittest.main()
