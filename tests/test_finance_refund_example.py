import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_TESTS = ROOT / "skill" / "scripts" / "run_tests.py"
VALIDATE_CASES = ROOT / "skill" / "scripts" / "validate_cases.py"
EXAMPLE_YAML = ROOT / "examples" / "finance-refund-retry.yaml"


class FinanceRefundHandler(BaseHTTPRequestHandler):
    duplicate_calls = 0

    def log_message(self, format, *args):
        return

    def do_POST(self):
        if self.path == "/api/finance/refunds/auth-required/retry":
            self._json(401, {"code": "UNAUTHENTICATED"})
            return

        role = self.headers.get("X-Operator-Role", "")
        if self.path == "/api/finance/refunds/high-value/retry":
            if role == "finance_manager":
                self._json(403, {"code": "REFUND_LIMIT_EXCEEDED"})
                return
            self._json(200, {"code": "OK"})
            return

        if self.path == "/api/finance/refunds/gateway-fail/retry":
            self._json(
                409,
                {
                    "code": "GATEWAY_FAILED",
                    "data": {
                        "ledgerUpdated": False,
                        "refundStatus": "failed",
                    },
                },
            )
            return

        if self.path == "/api/finance/refunds/duplicate/retry":
            FinanceRefundHandler.duplicate_calls += 1
            self._json(
                200,
                {
                    "code": "OK",
                    "data": {
                        "refundId": "duplicate",
                        "refundStatus": "processing",
                        "gatewayCallId": f"gw-call-{FinanceRefundHandler.duplicate_calls}",
                    },
                },
            )
            return

        if self.path == "/api/finance/refunds/audit-ok/retry":
            self._json(
                200,
                {
                    "code": "OK",
                    "data": {
                        "auditRecorded": True,
                        "operatorId": "finance-admin-001",
                    },
                },
            )
            return

        self._json(404, {"code": "NOT_FOUND"})

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FinanceRefundExampleTest(unittest.TestCase):
    def test_finance_refund_example_generates_gate_evidence(self):
        validate = subprocess.run(
            [sys.executable, str(VALIDATE_CASES), str(EXAMPLE_YAML)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, validate.returncode, validate.stderr + validate.stdout)

        server = HTTPServer(("127.0.0.1", 0), FinanceRefundHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                env_path = tmp_path / "env.yaml"
                report_path = tmp_path / "report.json"
                evidence_path = tmp_path / "automation_results.json"
                env_path.write_text(
                    f"FINANCE_REFUND_BASE_URL: http://127.0.0.1:{server.server_port}\n",
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
                self.assertIn("idempotency_risk", evidence["risk_domains"])
                self.assertIn("external_side_effect_risk", evidence["risk_domains"])

                suite = evidence["suites"][0]
                self.assertEqual("failed", suite["status"])
                self.assertEqual(5, suite["cases_total"])
                self.assertEqual(1, suite["cases_failed"])
                self.assertEqual(4, len(suite["passed_cases"]))

                failed_case = suite["failed_cases"][0]
                self.assertEqual("refund_retry_idempotency_001", failed_case["case_id"])
                self.assertEqual("duplicate_side_effect_risk", failed_case["risk_tag"])
                self.assertEqual("probable_bug", failed_case["classification"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
