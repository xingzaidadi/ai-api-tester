import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.failure_analyzer import analyze_report


class FailureAnalyzerTest(unittest.TestCase):
    def test_classifies_setup_auth_failure_as_env_issue(self):
        report = {
            "api": "POST /orders",
            "setup_errors": [
                {
                    "id": "create_product",
                    "response_status": 401,
                    "request": {"method": "POST", "url": "http://api/products"},
                    "failures": ["HTTP 401"],
                    "response_body": {"message": "unauthorized"},
                }
            ],
            "cases": [],
        }

        analysis = analyze_report(report)

        self.assertEqual("env_issue", analysis["findings"][0]["classification"])
        self.assertIn("HTTP 401", analysis["findings"][0]["reason"])

    def test_classifies_unresolved_variable_as_env_issue(self):
        report = {
            "api": "GET /orders",
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常查询",
                    "dimension": "functional_positive",
                    "priority": "P0",
                    "status": "error",
                    "request": {"method": "GET", "url": "{{ENV.API_BASE}}/orders"},
                    "error": "Invalid URL",
                }
            ],
        }

        analysis = analyze_report(report)

        self.assertEqual("env_issue", analysis["findings"][0]["classification"])
        self.assertIn("unresolved variables", analysis["findings"][0]["reason"])

    def test_classifies_500_as_probable_bug(self):
        report = {
            "api": "POST /orders",
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常创建",
                    "dimension": "functional_positive",
                    "priority": "P0",
                    "status": "fail",
                    "source": "OrderService.java:42",
                    "request": {"method": "POST", "url": "http://api/orders"},
                    "response_status": 500,
                    "response_body": {"error": "NullPointerException"},
                    "failures": ["[status] expected 200, got 500"],
                }
            ],
        }

        analysis = analyze_report(report)

        self.assertEqual("probable_bug", analysis["findings"][0]["classification"])
        self.assertEqual("P0", analysis["findings"][0]["severity"])

    def test_classifies_security_failure_as_probable_bug(self):
        source_file = ROOT / "tests" / "fixtures" / "spring-basic" / "src" / "main" / "java" / "com" / "example" / "order" / "OrderService.java"
        report = {
            "api": "GET /orders/1",
            "cases": [
                {
                    "id": "TC-AUTH-001",
                    "name": "水平越权应拒绝",
                    "dimension": "security_auth",
                    "priority": "P0",
                    "status": "fail",
                    "source": f"{source_file}:8",
                    "request": {"method": "GET", "url": "http://api/orders/1"},
                    "response_status": 200,
                    "response_body": {"data": {"id": 1}},
                    "failures": ["[status] expected 403, got 200"],
                }
            ],
        }

        context = {
            "test_basis": {
                "route": {"method": "GET", "path": "/orders/{id}"},
                "auth": [{"source": str(source_file), "line": 8, "evidence": "current user should own order"}],
            }
        }
        analysis = analyze_report(report, context=context)

        self.assertEqual("probable_bug", analysis["findings"][0]["classification"])
        self.assertEqual("疑似代码缺陷", analysis["findings"][0]["classification_zh"])
        self.assertIn("security", analysis["findings"][0]["reason"])
        self.assertIn("鉴权", analysis["findings"][0]["suggestion_zh"])
        self.assertIsNotNone(analysis["findings"][0]["source_context"])
        self.assertEqual(str(source_file), analysis["findings"][0]["source_context"]["file"])
        self.assertIn("auth", analysis["findings"][0]["context_evidence"])

    def test_classifies_missing_response_path_as_test_issue(self):
        report = {
            "api": "GET /orders",
            "cases": [
                {
                    "id": "TC-FUNC-001",
                    "name": "正常查询",
                    "dimension": "functional_positive",
                    "priority": "P1",
                    "status": "fail",
                    "source": "app.py:10",
                    "request": {"method": "GET", "url": "http://api/orders"},
                    "response_status": 200,
                    "response_body": {"data": {}},
                    "failures": ["[body.data.id] expected not null, got None"],
                }
            ],
        }

        analysis = analyze_report(report)

        self.assertEqual("test_issue", analysis["findings"][0]["classification"])
        self.assertIn("wrong response path", analysis["findings"][0]["reason"])
        self.assertEqual("用例问题", analysis["findings"][0]["classification_zh"])
        self.assertIn("JSON path", analysis["findings"][0]["suggestion_zh"])

    def test_resolves_relative_source_from_context_code_files(self):
        source_file = ROOT / "tests" / "fixtures" / "spring-basic" / "src" / "main" / "java" / "com" / "example" / "order" / "OrderService.java"
        report = {
            "api": "POST /orders",
            "cases": [
                {
                    "id": "TC-BOUND-001",
                    "name": "数量边界应拒绝",
                    "dimension": "boundary_value",
                    "priority": "P1",
                    "status": "fail",
                    "source": "OrderService.java:8 → if quantity < 1",
                    "request": {"method": "POST", "url": "http://api/orders"},
                    "response_status": 200,
                    "response_body": {"data": {"id": 1}},
                    "failures": ["[status] expected 400, got 200"],
                }
            ],
        }
        context = {
            "code_files": [{"path": str(source_file), "role": "service"}],
            "test_basis": {
                "fields": [
                    {
                        "name": "quantity",
                        "constraints": [{"type": "min", "value": 1}],
                        "source": str(source_file) + ":8",
                    }
                ]
            },
        }

        analysis = analyze_report(report, context=context)
        source_context = analysis["findings"][0]["source_context"]

        self.assertIsNotNone(source_context)
        self.assertEqual(str(source_file), source_context["file"])
        self.assertEqual(8, source_context["line"])
        self.assertIn("参数校验", analysis["findings"][0]["suggestion_zh"])


if __name__ == "__main__":
    unittest.main()
