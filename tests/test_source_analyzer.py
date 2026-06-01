import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.detector import ProjectDetector
from ai_api_tester.locator import CodeLocator
from ai_api_tester.source_analyzer import SourceAnalyzer


class SourceAnalyzerTest(unittest.TestCase):
    def _basis(self, fixture_name, url, method):
        project = ROOT / "tests" / "fixtures" / fixture_name
        info = ProjectDetector(str(project)).detect()
        ctx = CodeLocator(str(project), info).locate(url, method)
        return SourceAnalyzer(str(project), info).analyze(ctx)

    def test_spring_extracts_request_fields_and_constraints(self):
        basis = self._basis("spring-basic", "/api/v1/orders", "POST")
        fields = {field["name"]: field for field in basis["fields"]}

        self.assertEqual("createOrder", basis["route"]["handler"])
        self.assertTrue(fields["productId"]["required"])
        self.assertEqual("not_null", fields["productId"]["constraints"][0]["type"])
        self.assertEqual("min", fields["quantity"]["constraints"][0]["type"])
        self.assertEqual(1, fields["quantity"]["constraints"][0]["value"])
        self.assertTrue(any("request.getQuantity()" in item["condition"] for item in basis["branches"]))

    def test_spring_extracts_generic_request_body_inner_model(self):
        basis = self._basis("spring-basic", "/api/v1/wrapped-orders", "POST")
        fields = {field["name"]: field for field in basis["fields"]}

        self.assertEqual("createWrappedOrder", basis["route"]["handler"])
        self.assertTrue(any(model["name"] == "CreateOrderRequest" for model in basis["request_models"]))
        self.assertTrue(fields["productId"]["required"])
        self.assertEqual("not_null", fields["productId"]["constraints"][0]["type"])

    def test_fastapi_extracts_pydantic_fields_and_auth(self):
        basis = self._basis("fastapi-basic", "/api/v1/orders", "POST")
        fields = {field["name"]: field for field in basis["fields"]}

        self.assertEqual("create_order", basis["route"]["handler"])
        self.assertTrue(fields["product_id"]["required"])
        self.assertTrue(fields["quantity"]["required"])
        constraint_types = {item["type"] for item in fields["quantity"]["constraints"]}
        self.assertEqual({"ge", "le"}, constraint_types)
        self.assertTrue(any("Depends(current_user)" in item["evidence"] for item in basis["auth"]))


if __name__ == "__main__":
    unittest.main()
