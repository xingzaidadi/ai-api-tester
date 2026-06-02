import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
RUN_TESTS = ROOT / "skill" / "scripts" / "run_tests.py"
VALIDATE_CASES = ROOT / "skill" / "scripts" / "validate_cases.py"
EXAMPLE_YAML = ROOT / "examples" / "finance-sensitive-export.yaml"


class FinanceSensitiveExportHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/finance/reports/export":
            self._json(404, {"code": "NOT_FOUND"})
            return

        query = parse_qs(parsed.query)
        role = self.headers.get("X-Operator-Role", "")
        auth = self.headers.get("Authorization", "")
        project_id = self._first(query, "projectId")
        include_sensitive = self._first(query, "includeSensitive")
        bulk = self._first(query, "bulk")

        if not auth:
            self._json(401, {"code": "UNAUTHENTICATED"})
            return

        if role == "data_analyst" and include_sensitive == "true":
            self._json(403, {"code": "SENSITIVE_EXPORT_FORBIDDEN"})
            return

        if project_id == "unapproved-project" and bulk == "true":
            self._json(
                409,
                {
                    "code": "PROJECT_NOT_APPROVED",
                    "data": {"exportStarted": False},
                },
            )
            return

        if project_id == "approved-project":
            self._json(
                200,
                {
                    "code": "OK",
                    "data": {
                        "rowCount": 2,
                        "rows": [
                            {"userId": "u-001", "amount": 128.0, "maskedName": "A***"},
                            {"userId": "u-002", "amount": 256.0, "maskedName": "B***"},
                        ],
                    },
                },
            )
            return

        if project_id == "masking-regression":
            self._json(
                200,
                {
                    "code": "OK",
                    "data": {
                        "rowCount": 1,
                        "rows": [
                            {
                                "userId": "u-003",
                                "amount": 512.0,
                                "phone": "13800000000",
                            }
                        ],
                    },
                },
            )
            return

        self._json(404, {"code": "NOT_FOUND"})

    def _first(self, query, key):
        values = query.get(key) or [""]
        return values[0]

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FinanceSensitiveExportExampleTest(unittest.TestCase):
    def test_finance_sensitive_export_example_generates_gate_evidence(self):
        validate = subprocess.run(
            [sys.executable, str(VALIDATE_CASES), str(EXAMPLE_YAML)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, validate.returncode, validate.stderr + validate.stdout)

        server = HTTPServer(("127.0.0.1", 0), FinanceSensitiveExportHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                env_path = tmp_path / "env.yaml"
                report_path = tmp_path / "report.json"
                evidence_path = tmp_path / "automation_results.json"
                env_path.write_text(
                    f"FINANCE_EXPORT_BASE_URL: http://127.0.0.1:{server.server_port}\n",
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(RUN_TESTS),
                        str(EXAMPLE_YAML),
                        "--env-file",
                        str(env_path),
                        "--report",
                        str(report_path),
                        "--automation-results",
                        str(evidence_path),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

                self.assertEqual(1, result.returncode, result.stderr + result.stdout)

                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(5, report["summary"]["total"])
                self.assertEqual(4, report["summary"]["passed"])
                self.assertEqual(1, report["summary"]["failed"])

                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                self.assertEqual("ai-api-tester", evidence["source_tool"])
                self.assertIn("data_export_risk", evidence["risk_domains"])
                self.assertIn("auditability_risk", evidence["risk_domains"])
                self.assertIn("auth_risk", evidence["risk_domains"])

                suite = evidence["suites"][0]
                self.assertEqual("failed", suite["status"])
                self.assertEqual(5, suite["cases_total"])
                self.assertEqual(1, suite["cases_failed"])
                self.assertEqual(4, len(suite["passed_cases"]))

                failed_case = suite["failed_cases"][0]
                self.assertEqual("finance_export_masking_regression_001", failed_case["case_id"])
                self.assertEqual("sensitive_export_risk", failed_case["risk_tag"])
                self.assertEqual("probable_bug", failed_case["classification"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
