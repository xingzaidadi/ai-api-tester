"""
AI API Tester — CLI 入口

用法：
    # 生成测试用例（输出代码上下文供 AI 生成 YAML）
    ai-tester gen /api/v1/order/create --project ./my-project

    # 执行测试用例
    ai-tester run tests/order/create-order.yaml --env test

    # 分析项目风险
    ai-tester risk /api/v1/order/create --project ./my-project

    # 探测项目类型
    ai-tester detect --project ./my-project
"""

import sys
import json
import argparse
import time
from pathlib import Path

from .detector import ProjectDetector
from .locator import CodeLocator
from .analyzer import GitAnalyzer, SchemaAnalyzer
from .engine import TestEngine
from .report import ReportGenerator


def cmd_detect(args):
    """探测项目类型"""
    detector = ProjectDetector(args.project)
    info = detector.detect()
    print(f"🔍 项目探测结果:")
    print(f"   语言: {info.language}")
    print(f"   框架: {info.framework}")
    print(f"   源码目录: {info.entry_dirs}")
    print(f"   文件类型: {info.file_ext}")


def cmd_locate(args):
    """从 URL 反查代码"""
    detector = ProjectDetector(args.project)
    info = detector.detect()
    print(f"🔍 项目: {info.language}/{info.framework}")

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"❌ 未找到匹配 '{args.url}' 的代码文件")
        return

    print(f"\n📂 找到 {len(ctx.files)} 个相关文件:")
    for f in ctx.files:
        print(f"   [{f.role}] {f.path}" + (f" (line {f.line_match})" if f.line_match else ""))

    if ctx.call_chain:
        print(f"\n🔗 调用链:")
        for chain in ctx.call_chain:
            print(f"   {chain}")


def cmd_gen(args):
    """生成测试上下文（供 AI 生成用例）"""
    detector = ProjectDetector(args.project)
    info = detector.detect()
    print(f"🔍 项目: {info.language}/{info.framework}")

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"❌ 未找到匹配 '{args.url}' 的代码文件")
        return

    print(f"📂 找到 {len(ctx.files)} 个相关文件")

    git_analyzer = GitAnalyzer(args.project)
    risk_info = git_analyzer.analyze_risk([f.path for f in ctx.files])
    print(f"📊 风险评分: {risk_info.risk_score:.1f}/10")
    for factor in risk_info.risk_factors:
        print(f"   • {factor}")

    schema_analyzer = SchemaAnalyzer(args.project, info.language)
    model_files = [f.path for f in ctx.files if f.role in ("model", "mapper")]
    constraints = schema_analyzer.analyze_entity(model_files)
    if constraints:
        print(f"📋 发现 {len(constraints)} 个 Schema 约束")

    output = {
        "project": {
            "language": info.language,
            "framework": info.framework,
        },
        "api": {
            "url": args.url,
            "method": args.method or "unknown",
        },
        "code_files": [
            {
                "path": f.path,
                "role": f.role,
                "content": f.content[:5000],
            }
            for f in ctx.files
        ],
        "risk": {
            "score": risk_info.risk_score,
            "factors": risk_info.risk_factors,
            "recent_changes": risk_info.recent_changes,
            "fix_commits": risk_info.recent_fix_commits,
        },
        "schema_constraints": [
            {
                "table": c.table,
                "column": c.column,
                "type": c.constraint_type,
                "detail": c.detail,
            }
            for c in constraints
        ],
    }

    output_path = args.output or f"tests/{args.url.strip('/').replace('/', '_')}_context.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n✅ 上下文已输出到: {output_path}")
    print(f"   请将此文件内容 + prompts/generate_cases.md 一起交给 AI 生成测试用例")


def cmd_run(args):
    """执行测试用例"""
    import yaml

    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"❌ 文件不存在: {yaml_path}")
        return

    with open(yaml_path, "r", encoding="utf-8") as f:
        suite = yaml.safe_load(f)

    print(f"🚀 执行测试: {suite.get('metadata', {}).get('api', yaml_path.name)}")
    print(f"   用例数: {len(suite.get('cases', []))}")
    print()

    env = {}
    if args.env_file:
        env_path = Path(args.env_file)
        if env_path.exists():
            with open(env_path, "r") as f:
                env = yaml.safe_load(f) or {}

    engine = TestEngine(env=env)
    start = time.time()
    result = engine.run_suite(suite)

    reporter = ReportGenerator()
    print(reporter.console_report(result))

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(reporter.json_report(result))
        print(f"📄 报告已保存: {report_path}")

    sys.exit(0 if result.failed == 0 and result.errored == 0 else 1)


def cmd_risk(args):
    """分析接口风险"""
    detector = ProjectDetector(args.project)
    info = detector.detect()

    locator = CodeLocator(args.project, info)
    ctx = locator.locate(args.url, args.method)

    if not ctx.files:
        print(f"❌ 未找到代码")
        return

    git_analyzer = GitAnalyzer(args.project)
    risk_info = git_analyzer.analyze_risk([f.path for f in ctx.files])

    print(f"\n📊 风险分析: {args.url}")
    print(f"{'─' * 40}")
    print(f"   评分: {risk_info.risk_score:.1f}/10")
    print(f"   近30天修改: {risk_info.recent_changes} 次")
    print(f"   最后修改: {risk_info.last_modified}")

    if risk_info.recent_fix_commits:
        print(f"\n   🐛 近期 fix 提交:")
        for commit in risk_info.recent_fix_commits:
            print(f"      {commit}")

    if risk_info.hot_files:
        print(f"\n   🔥 项目热点文件:")
        for f in risk_info.hot_files:
            print(f"      {f}")

    if risk_info.risk_factors:
        print(f"\n   ⚠️ 风险因素:")
        for f in risk_info.risk_factors:
            print(f"      • {f}")


def main():
    parser = argparse.ArgumentParser(
        prog="ai-tester",
        description="AI API Tester — AI 驱动的接口自动化测试工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_detect = subparsers.add_parser("detect", help="探测项目类型")
    p_detect.add_argument("--project", "-p", default=".", help="项目路径")

    p_locate = subparsers.add_parser("locate", help="从 URL 反查代码")
    p_locate.add_argument("url", help="接口 URL 路径")
    p_locate.add_argument("--method", "-m", default=None, help="HTTP 方法")
    p_locate.add_argument("--project", "-p", default=".", help="项目路径")

    p_gen = subparsers.add_parser("gen", help="生成测试上下文")
    p_gen.add_argument("url", help="接口 URL 路径")
    p_gen.add_argument("--method", "-m", default="POST", help="HTTP 方法")
    p_gen.add_argument("--project", "-p", default=".", help="项目路径")
    p_gen.add_argument("--output", "-o", default=None, help="输出路径")

    p_run = subparsers.add_parser("run", help="执行测试用例")
    p_run.add_argument("yaml_file", help="YAML 测试用例文件")
    p_run.add_argument("--env-file", "-e", default=None, help="环境变量文件")
    p_run.add_argument("--report", "-r", default=None, help="报告输出路径")

    p_risk = subparsers.add_parser("risk", help="分析接口风险")
    p_risk.add_argument("url", help="接口 URL 路径")
    p_risk.add_argument("--method", "-m", default=None, help="HTTP 方法")
    p_risk.add_argument("--project", "-p", default=".", help="项目路径")

    args = parser.parse_args()

    commands = {
        "detect": cmd_detect,
        "locate": cmd_locate,
        "gen": cmd_gen,
        "run": cmd_run,
        "risk": cmd_risk,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
