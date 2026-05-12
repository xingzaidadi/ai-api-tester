#!/usr/bin/env python3
"""Convert test reports to CI-friendly formats (JUnit XML, Markdown summary)."""

import sys
import json
import argparse
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


def report_to_junit_xml(report: dict) -> str:
    """Convert a report dict to JUnit XML format.

    Args:
        report: Test report with keys: api, total, passed, failed, errored,
                duration_ms, and cases list.

    Returns:
        Pretty-printed JUnit XML string.
    """
    testsuites = Element("testsuites")
    testsuite = SubElement(
        testsuites,
        "testsuite",
        name=report["api"],
        tests=str(report["total"]),
        failures=str(report["failed"]),
        errors=str(report["errored"]),
        time=str(report["duration_ms"] / 1000),
    )

    for case in report.get("cases", []):
        testcase = SubElement(
            testsuite,
            "testcase",
            name=f"{case['case_id']}: {case['name']}",
            classname=case["dimension"],
            time=str(case["duration_ms"] / 1000),
        )

        status = case.get("status", "")
        if status == "fail":
            failure_msg = "; ".join(case.get("failures", []))
            SubElement(
                testcase,
                "failure",
                message=failure_msg,
                type="AssertionError",
            )
        elif status == "error":
            SubElement(
                testcase,
                "error",
                message=case.get("error_message", ""),
                type="RuntimeError",
            )
        elif status == "skip":
            SubElement(testcase, "skipped", message="skipped")

    raw_xml = tostring(testsuites, encoding="unicode")
    pretty = parseString(raw_xml).toprettyxml(indent="  ")
    # Remove extra XML declaration if present, keep just one
    lines = pretty.split("\n")
    return "\n".join(lines)


def report_to_markdown(report: dict, analysis: dict = None) -> str:
    """Convert report and optional analysis to a Markdown summary.

    Args:
        report: Test report dict.
        analysis: Optional analysis dict with findings list.

    Returns:
        Markdown-formatted string suitable for PR comments.
    """
    lines = []
    lines.append(f"## API Test Results: {report['api']}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total | {report['total']} |")
    lines.append(f"| Passed | {report['passed']} |")
    lines.append(f"| Failed | {report['failed']} |")
    lines.append(f"| Errors | {report['errored']} |")
    lines.append(f"| Duration | {report['duration_ms']}ms |")
    lines.append("")

    failed_cases = [
        c for c in report.get("cases", []) if c.get("status") == "fail"
    ]

    if not failed_cases and report.get("failed", 0) == 0 and report.get("errored", 0) == 0:
        lines.append("All tests passed!")
        lines.append("")
    else:
        if failed_cases:
            lines.append("### Failed Cases")
            lines.append("")
            lines.append("| ID | Name | Dimension | Priority | Failure |")
            lines.append("|----|------|-----------|----------|---------|")
            for c in failed_cases:
                failure_msg = "; ".join(c.get("failures", []))
                lines.append(
                    f"| {c['case_id']} | {c['name']} | {c['dimension']} "
                    f"| {c['priority']} | {failure_msg} |"
                )
            lines.append("")

    if analysis and analysis.get("findings"):
        lines.append("### Failure Analysis")
        lines.append("")
        for finding in analysis["findings"]:
            lines.append(
                f"- **{finding['case_id']}**: {finding['classification']} - "
                f"{finding['reason']}"
            )
            lines.append(f"  - Suggestion: {finding['suggestion_zh']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert test reports to CI-friendly formats."
    )
    parser.add_argument("report", help="Path to report.json")
    parser.add_argument(
        "--format",
        "-f",
        choices=["junit", "markdown"],
        default="junit",
        help="Output format (default: junit)",
    )
    parser.add_argument(
        "--analysis",
        "-a",
        default=None,
        help="Path to analysis.json (for markdown format)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"Error: report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    if args.format == "junit":
        output = report_to_junit_xml(report)
    else:
        analysis = None
        if args.analysis:
            analysis_path = Path(args.analysis)
            if analysis_path.exists():
                with open(analysis_path, "r", encoding="utf-8") as f:
                    analysis = json.load(f)
        output = report_to_markdown(report, analysis)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
