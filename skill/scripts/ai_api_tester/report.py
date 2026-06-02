"""
测试报告生成器
"""

import json
from datetime import datetime
from .engine import SuiteResult, CaseResult


class ReportGenerator:
    def console_report(self, result: SuiteResult) -> str:
        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"  [REPORT] 测试报告：{result.api}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"  总计: {result.total} | [PASS] 通过: {result.passed} | [FAIL] 失败: {result.failed} | [ERROR] 错误: {result.errored} | [SKIP] 跳过: {result.skipped}")
        lines.append(f"  耗时: {result.duration_ms}ms")
        lines.append(f"  维度覆盖: {', '.join(result.dimensions_covered)}")
        lines.append("")

        # 通过的用例（简要）
        passed = [c for c in result.cases if c.status == "pass"]
        if passed:
            lines.append(f"  [PASS] 通过 ({len(passed)}):")
            for c in passed:
                lines.append(f"     [{c.priority}][{c.dimension}] {c.name} ({c.duration_ms}ms)")
            lines.append("")

        # 失败的用例（详细）
        failed = [c for c in result.cases if c.status == "fail"]
        if failed:
            lines.append(f"  [FAIL] 失败 ({len(failed)}):")
            for c in failed:
                lines.append(f"     [{c.priority}][{c.dimension}] {c.name}")
                if c.source:
                    lines.append(f"        来源: {c.source}")
                lines.append(f"        响应: HTTP {c.response_status}")
                for f in c.failures:
                    lines.append(f"        断言: {f}")
                lines.append("")

        # 错误的用例
        errored = [c for c in result.cases if c.status == "error"]
        if errored:
            lines.append(f"  [ERROR] 错误 ({len(errored)}):")
            for c in errored:
                lines.append(f"     [{c.priority}][{c.dimension}] {c.name}")
                lines.append(f"        错误: {c.error_message}")
            lines.append("")

        lines.append("=" * 60)

        # 维度覆盖统计
        dimension_stats = {}
        for c in result.cases:
            dim = c.dimension
            if dim not in dimension_stats:
                dimension_stats[dim] = {"total": 0, "pass": 0, "fail": 0}
            dimension_stats[dim]["total"] += 1
            if c.status == "pass":
                dimension_stats[dim]["pass"] += 1
            elif c.status == "fail":
                dimension_stats[dim]["fail"] += 1

        if dimension_stats:
            lines.append("")
            lines.append("  [STATS] 维度覆盖统计:")
            for dim, stats in dimension_stats.items():
                rate = stats["pass"] / stats["total"] * 100 if stats["total"] > 0 else 0
                icon = "[PASS]" if rate == 100 else "[WARN]" if rate >= 50 else "[FAIL]"
                lines.append(f"     {icon} {dim}: {stats['pass']}/{stats['total']} ({rate:.0f}%)")

        lines.append("")
        return "\n".join(lines)

    def json_report(self, result: SuiteResult) -> str:
        report = {
            "api": result.api,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": result.total,
                "passed": result.passed,
                "failed": result.failed,
                "errored": result.errored,
                "skipped": result.skipped,
                "duration_ms": result.duration_ms,
                "pass_rate": f"{result.passed / result.total * 100:.1f}%" if result.total > 0 else "0%",
            },
            "dimensions_covered": result.dimensions_covered,
            "setup_errors": result.setup_errors,
            "cases": [
                {
                    "id": c.case_id,
                    "name": c.name,
                    "dimension": c.dimension,
                    "priority": c.priority,
                    "status": c.status,
                    "duration_ms": c.duration_ms,
                    "source": c.source,
                    "request": c.request,
                    "failures": c.failures,
                    "error": c.error_message,
                    "response_status": c.response_status,
                    "response_headers": c.response_headers,
                    "response_body": c.response_body,
                    "extracted_variables": c.extracted_variables,
                    "teardown_errors": c.teardown_errors,
                }
                for c in result.cases
            ],
            "failed_cases_for_ai_analysis": [
                {
                    "id": c.case_id,
                    "name": c.name,
                    "dimension": c.dimension,
                    "source": c.source,
                    "expected": c.failures,
                    "request": c.request,
                    "actual_status": c.response_status,
                    "actual_headers": c.response_headers,
                    "actual_body": c.response_body,
                    "teardown_errors": c.teardown_errors,
                }
                for c in result.cases if c.status == "fail"
            ],
        }
        return json.dumps(report, ensure_ascii=False, indent=2)

    def markdown_report(self, result: SuiteResult) -> str:
        lines = []
        lines.append(f"# 接口测试报告：{result.api}")
        lines.append("")
        lines.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**结果**: {result.passed}/{result.total} 通过 ({result.passed / result.total * 100:.0f}%)" if result.total > 0 else "")
        lines.append(f"**耗时**: {result.duration_ms}ms")
        lines.append("")

        # 汇总表格
        lines.append("## 用例结果")
        lines.append("")
        lines.append("| ID | 名称 | 维度 | 优先级 | 状态 | 耗时 |")
        lines.append("|----|------|------|--------|------|------|")
        for c in result.cases:
            status_icon = {"pass": "[PASS]", "fail": "[FAIL]", "error": "[ERROR]", "skip": "[SKIP]"}.get(c.status, "?")
            lines.append(f"| {c.case_id} | {c.name} | {c.dimension} | {c.priority} | {status_icon} | {c.duration_ms}ms |")

        # 失败详情
        failed = [c for c in result.cases if c.status == "fail"]
        if failed:
            lines.append("")
            lines.append("## 失败详情")
            for c in failed:
                lines.append("")
                lines.append(f"### {c.case_id}: {c.name}")
                lines.append(f"- **维度**: {c.dimension}")
                lines.append(f"- **来源**: `{c.source}`")
                lines.append(f"- **响应状态**: {c.response_status}")
                lines.append(f"- **断言失败**:")
                for f in c.failures:
                    lines.append(f"  - {f}")

        lines.append("")
        return "\n".join(lines)
