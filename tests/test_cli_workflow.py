import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEN_CONTEXT = ROOT / "skill" / "scripts" / "gen_context.py"
VALIDATE_CASES = ROOT / "skill" / "scripts" / "validate_cases.py"


class CliWorkflowTest(unittest.TestCase):
    def test_gen_context_cli_outputs_spring_test_basis(self):
        output_path = Path(tempfile.gettempdir()) / "ai-api-tester-spring-context-test.json"
        project = ROOT / "tests" / "fixtures" / "spring-basic"

        result = subprocess.run(
            [
                sys.executable,
                str(GEN_CONTEXT),
                "/api/v1/orders",
                str(project),
                "--method",
                "POST",
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        data = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("spring-boot", data["project"]["framework"])
        self.assertEqual("createOrder", data["test_basis"]["route"]["handler"])

        fields = {field["name"]: field for field in data["test_basis"]["fields"]}
        self.assertIn("productId", fields)
        self.assertIn("quantity", fields)
        self.assertTrue(fields["productId"]["required"])
        self.assertEqual("min", fields["quantity"]["constraints"][0]["type"])

    def test_gen_context_cli_outputs_fastapi_test_basis(self):
        output_path = Path(tempfile.gettempdir()) / "ai-api-tester-fastapi-context-test.json"
        project = ROOT / "tests" / "fixtures" / "fastapi-basic"

        result = subprocess.run(
            [
                sys.executable,
                str(GEN_CONTEXT),
                "/api/v1/orders",
                str(project),
                "--method",
                "POST",
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        data = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("fastapi", data["project"]["framework"])
        self.assertEqual("create_order", data["test_basis"]["route"]["handler"])

        fields = {field["name"]: field for field in data["test_basis"]["fields"]}
        self.assertTrue(fields["quantity"]["required"])
        self.assertEqual({"ge", "le"}, {item["type"] for item in fields["quantity"]["constraints"]})
        self.assertTrue(data["test_basis"]["auth"])

    def test_validate_cases_cli_accepts_demo_yaml(self):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_CASES),
                str(ROOT / "examples" / "demo-order-create.yaml"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertIn("YAML validation passed.", result.stdout)


if __name__ == "__main__":
    unittest.main()
