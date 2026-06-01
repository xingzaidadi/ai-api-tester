---
name: ai-api-tester
description: Source-code-driven API test generation and execution. Use when users want Codex to locate API implementation code from a URL path, generate executable YAML API test cases, validate test case format, run API tests, analyze Git risk for an endpoint, or explain API test failures. Supports initial workflows for Java Spring Boot, Python FastAPI/Django/Flask, Go Gin/Echo, and Node Express/NestJS, with strongest current support for direct route lookup and HTTP execution.
---

# AI API Tester

Generate source-backed API test cases, validate the YAML, execute HTTP tests, and analyze failures.

## Path Rules

- Resolve all script and reference paths relative to this skill directory.
- Run scripts with `python3`.
- The skill is self-contained: scripts import from `scripts/ai_api_tester/`, not from the user's repository.

## Workflow

### Initialize Project

When a user wants to start using ai-api-tester on their project, or says "初始化" / "setup" / "init":

1. Run `python3 scripts/init_project.py <project_path>` to detect the project and create env.yaml template.
2. Ask the user to fill in the `base_url` and auth tokens in the generated `env.yaml`.
3. Proceed to any of the workflows below.

### Generate Test Cases

1. Run `python3 scripts/detect.py <project_path>` to identify language and framework.
2. Run `python3 scripts/locate.py <url> <project_path> --method <METHOD>` to locate source files.
3. Run `python3 scripts/gen_context.py <url> <project_path> --method <METHOD> --output <context.json>` to produce code context and Git risk.
4. Read `test_basis` from the generated context first, then inspect `code_files` to confirm assumptions. Extract request parameters, validation rules, branches, auth rules, state changes, persistence operations, external calls, and sensitive fields.
5. Read `references/context_format.md`, `references/dimensions.md`, and `references/yaml_format.md`.
6. Generate YAML using only runner-supported fields.
7. Run `python3 scripts/validate_cases.py <cases.yaml>`.
8. If validation fails, fix the YAML and validate again.
9. Show a dimension coverage matrix and wait for user confirmation before executing tests.

### Execute Tests

1. Confirm the environment config file or required `ENV.*` variables are available.
2. Run `python3 scripts/validate_cases.py <cases.yaml>`.
3. Run `python3 scripts/run_tests.py <cases.yaml> --env-file <env.yaml> --report <report.json>`.
4. If any case fails or errors, run `python3 scripts/analyze_failures.py <report.json> --context-json <context.json> --output <analysis.json>` when a context file is available. Omit `--context-json` if no context file exists.
5. If the user needs Agentic QA Gate integration, run `python3 scripts/export_automation_results.py <report.json> --analysis <analysis.json> --output <automation_results.json>`.
6. Display the result summary and failure analysis.
7. For each `probable_bug`, read the `source` location, compare expected vs actual, and provide a source-backed fix suggestion.

### Analyze Risk

Run `python3 scripts/risk.py <url> <project_path> --method <METHOD>` to show risk score, recent changes, fix commits, hot files, and risk factors.

### One-Command Mode

For batch testing all discovered APIs in a project:

1. Run `python3 scripts/auto.py <project_path> --validate-only` to list discovered routes.
2. Run `python3 scripts/auto.py <project_path> --output-dir <dir>` to generate context for all routes.
3. For each generated `context.json`, read the `test_basis` and generate YAML test cases.
4. Run `python3 scripts/validate_cases.py <cases.yaml>` for each generated YAML.
5. Run `python3 scripts/run_tests.py <cases.yaml> --env-file <env.yaml> --report <report.json>` for each.
6. Aggregate results and display overall health summary.

When the user says "帮我测这个项目的所有接口" or "test all APIs in this project", use this workflow.

### Incremental Mode

For testing only APIs affected by recent code changes:

1. Run `python3 scripts/diff_detect.py <project_path> --base <branch>` to identify affected routes.
2. If no routes affected, report "No API changes detected" and stop.
3. For each affected route, run the Generate Test Cases workflow (steps 1-9).
4. Execute and analyze as usual.

When the user says "帮我测这次改动涉及的接口", "test my changes", or "incremental test", use this workflow. Default base is `main` for PR workflows.

### Heal Stale Cases

For updating existing test cases when source code has changed:

1. Run `python3 scripts/heal.py <cases.yaml> <project_path> --output <heal_report.json>`.
2. Read the heal report to identify stale, broken, or outdated cases.
3. For each issue found, update the YAML case accordingly:
   - `stale`: field was renamed → update request body field names and expect paths.
   - `broken`: route path changed → update request URLs.
   - `outdated`: constraint values changed → update boundary test values.
4. Re-validate the updated YAML with `python3 scripts/validate_cases.py`.

## Scripts

- `scripts/detect.py <project_path>`: detect language/framework.
- `scripts/locate.py <url> <project_path> [--method METHOD]`: locate source files from URL.
- `scripts/gen_context.py <url> <project_path> [--method METHOD] [--output PATH]`: generate context JSON.
- `scripts/validate_cases.py <yaml_file>`: validate YAML without executing HTTP requests.
- `scripts/run_tests.py <yaml_file> [--env-file PATH] [--report PATH]`: execute test suite.
- `scripts/analyze_failures.py <report.json> [--output PATH]`: classify failures from JSON report.
- `scripts/export_automation_results.py <report.json> --output PATH [--analysis PATH]`: export Agentic QA Gate `automation_results.json`.
- `scripts/risk.py <url> <project_path> [--method METHOD]`: analyze Git-based risk.
- `scripts/auto.py <project_path> [--url URL] [--method METHOD] [--output-dir DIR] [--validate-only]`: one-command pipeline for batch or single-API context generation.
- `scripts/diff_detect.py <project_path> [--base REF] [--output PATH]`: detect APIs affected by git changes.
- `scripts/heal.py <cases.yaml> <project_path> [--output PATH]`: detect stale test cases and suggest fixes.
- `scripts/learn_history.py <output_dir> [--save PATH]`: learn from historical reports and generate risk profile.
- `scripts/dashboard.py <output_dir> [--output PATH]`: generate HTML dashboard from historical reports.
- `scripts/ci_reporter.py <report.json> [--format junit|markdown] [--analysis PATH] [--output PATH]`: convert reports to CI formats.
- `scripts/init_project.py <project_path> [--output-dir DIR]`: initialize a project for ai-api-tester (creates env.yaml, output dir, prints guide).

## References

- `references/yaml_format.md`: executable YAML schema and examples.
- `references/assertions.md`: supported assertion syntax.
- `references/dimensions.md`: test dimensions, generation conditions, and current execution limits.
- `references/routing_support.md`: currently supported route extraction patterns and known limits.
- `references/context_format.md`: generated context JSON structure and how to use `test_basis`.
- `references/failure_analysis.md`: failure classification types, heuristics, and workflow.

## Generation Rules

- Every generated case MUST have a real `source` value pointing to a file and line or directly observed code construct.
- Use Chinese for case names and failure analysis.
- Output a concise test-basis summary before the YAML: business flow, parameters, branches, risks, applicable dimensions, and skipped dimensions. Do not output private chain-of-thought.
- Do not generate fields that `scripts/validate_cases.py` rejects.
- Do not generate `concurrency` cases yet; show the concurrency dimension as skipped when applicable because the current runner does not execute concurrent requests.
- Do not force dimensions that do not apply. Explain skipped dimensions in the coverage matrix.
- YAML must pass `scripts/validate_cases.py` before `scripts/run_tests.py` is used.
- When context contains `risk_profile`, generate 1-2 extra P0 cases for dimensions with >30% historical failure rate. Prioritize testing modules with high bug density.

## Failure Analysis Format

For each failed case, output:

```text
TC-XXX-NNN: case name
Type: probable_bug | test_issue | env_issue
Location: FileName:lineNumber
Reason: what went wrong
Expected: expected result
Actual: actual result
Fix: specific suggestion
Severity: P0/P1/P2
```
