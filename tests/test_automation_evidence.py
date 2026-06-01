import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.automation_evidence import build_automation_evidence


class AutomationEvidenceTest(unittest.TestCase):
    def _report(self):
        return {
            "api": "POST /api/refunds/retry",
            "summary": {
                "total": 3,
                "passed": 1,
                "failed": 1,
                "errored": 1,
                "skipped": 0,
            },
            "dimensions_covered": ["idempotency", "data_consistency"],
            "setup_errors": [],
            "cases": [
                {
                    "id": "refund_retry_contract_001",
                    "name": "正常退款重试",
                    "dimension": "idempotency",
                    "priority": "P0",
                    "status": "pass",
                },
                {
                    "id": "refund_retry_idempotency_001",
                    "name": "相同幂等键不能重复退款",
                    "dimension": "idempotency",
                    "priority": "P0",
                    "status": "fail",
                    "failures": ["gateway refund called twice"],
                },
                {
                    "id": "refund_retry_external_failure_001",
                    "name": "外部成功本地失败需要补偿",
                    "dimension": "data_consistency",
                    "priority": "P0",
                    "status": "error",
                    "error": "connection refused",
                },
            ],
        }

    def _analysis(self):
        return {
            "findings": [
                {
                    "id": "refund_retry_idempotency_001",
                    "classification": "probable_bug",
                    "reason": "business rule or validation assertion failed",
                },
                {
                    "id": "refund_retry_external_failure_001",
                    "classification": "env_issue",
                    "reason": "request could not reach the target service",
                },
            ]
        }

    def test_builds_gate_automation_evidence_from_report_and_analysis(self):
        evidence = build_automation_evidence(
            self._report(),
            self._analysis(),
            run_id="refund_retry_api_validation_2026_06_01",
            report_path="outputs/report.json",
        )

        self.assertEqual("0.1", evidence["schema_version"])
        self.assertEqual("ai-api-tester", evidence["source_tool"])
        self.assertIn("idempotency_risk", evidence["risk_domains"])
        self.assertIn("external_side_effect_risk", evidence["risk_domains"])

        suite = evidence["suites"][0]
        self.assertEqual("failed", suite["status"])
        self.assertEqual(3, suite["cases_total"])
        self.assertEqual(2, suite["cases_failed"])
        self.assertEqual(1, len(suite["passed_cases"]))
        self.assertEqual(2, len(suite["failed_cases"]))

        failed = {case["case_id"]: case for case in suite["failed_cases"]}
        self.assertEqual("probable_bug", failed["refund_retry_idempotency_001"]["classification"])
        self.assertEqual("env_issue", failed["refund_retry_external_failure_001"]["classification"])
        self.assertEqual("duplicate_side_effect_risk", failed["refund_retry_idempotency_001"]["risk_tag"])
        self.assertIn("#cases/refund_retry_idempotency_001", failed["refund_retry_idempotency_001"]["evidence"])

    def test_export_cli_writes_automation_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_path = tmp_path / "report.json"
            analysis_path = tmp_path / "analysis.json"
            output_path = tmp_path / "automation_results.json"
            report_path.write_text(json.dumps(self._report(), ensure_ascii=False), encoding="utf-8")
            analysis_path.write_text(json.dumps(self._analysis(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skill" / "scripts" / "export_automation_results.py"),
                    str(report_path),
                    "--analysis",
                    str(analysis_path),
                    "--output",
                    str(output_path),
                    "--run-id",
                    "cli_run",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("cli_run", payload["run_id"])
            self.assertEqual("failed", payload["suites"][0]["status"])


if __name__ == "__main__":
    unittest.main()
