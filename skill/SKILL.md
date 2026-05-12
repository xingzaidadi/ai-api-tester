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
5. Display the result summary and failure analysis.
6. For each `probable_bug`, read the `source` location, compare expected vs actual, and provide a source-backed fix suggestion.

### Analyze Risk

Run `python3 scripts/risk.py <url> <project_path> --method <METHOD>` to show risk score, recent changes, fix commits, hot files, and risk factors.

## Scripts

- `scripts/detect.py <project_path>`: detect language/framework.
- `scripts/locate.py <url> <project_path> [--method METHOD]`: locate source files from URL.
- `scripts/gen_context.py <url> <project_path> [--method METHOD] [--output PATH]`: generate context JSON.
- `scripts/validate_cases.py <yaml_file>`: validate YAML without executing HTTP requests.
- `scripts/run_tests.py <yaml_file> [--env-file PATH] [--report PATH]`: execute test suite.
- `scripts/analyze_failures.py <report.json> [--output PATH]`: classify failures from JSON report.
- `scripts/risk.py <url> <project_path> [--method METHOD]`: analyze Git-based risk.

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
