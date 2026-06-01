# AI API Tester

AI API Tester is a Codex skill for source-code-driven API testing. It locates API implementation code from a URL path, generates structured test context, validates executable YAML test suites, runs HTTP tests, and classifies failures with source-backed evidence.

The project is currently skill-first: the self-contained runtime lives under `skill/`. The older root-level `lib/` and `prompts/` folders are retained for compatibility and reference, but `skill/` is the source of truth for Codex usage.

## Current Capabilities

- Detect project language/framework.
- Locate API source files from method + URL.
- Extract route information for Spring Boot and FastAPI.
- Generate structured context JSON with `test_basis`.
- Validate YAML test cases before execution.
- Execute HTTP test suites.
- Support setup, teardown, extracts, params/query, response-time checks, and smart assertions.
- Generate JSON reports with resolved requests and response details.
- Analyze failures into `env_issue`, `test_issue`, and `probable_bug`.
- Export Agentic QA Gate `automation_results.json` evidence.
- Produce Chinese failure summaries with source snippets and optional `test_basis` evidence.

## Supported Frameworks

Strongest current support:

- Java Spring Boot
- Python FastAPI

Basic or fallback support:

- Python Django/Flask
- Go Gin/Echo
- Node Express/NestJS

Unsupported or partial areas are documented in `skill/references/routing_support.md`.

## Install As A Codex Skill

Copy the skill folder into Codex skills:

```bash
mkdir -p ~/.codex/skills
cp -R skill ~/.codex/skills/ai-api-tester
```

Then use `$ai-api-tester` in Codex. The skill scripts are self-contained and import from `skill/scripts/ai_api_tester/`.

## Command Workflow

All commands below are run from the skill directory.

### 1. Detect Project

```bash
python3 scripts/detect.py /path/to/project
```

### 2. Locate API Source

```bash
python3 scripts/locate.py /api/v1/orders /path/to/project --method POST
```

### 3. Generate Context

```bash
python3 scripts/gen_context.py /api/v1/orders /path/to/project \
  --method POST \
  --output /tmp/order-context.json
```

The context includes:

- `route`
- `request_models`
- `fields`
- `auth`
- `branches`
- `state_changes`
- `external_calls`
- `sensitive_fields`
- source snippets
- Git risk signals

See `skill/references/context_format.md`.

### 4. Generate And Validate YAML

Use the context JSON plus `skill/references/yaml_format.md`, `skill/references/dimensions.md`, and `skill/references/assertions.md` to generate a YAML suite.

Validate before execution:

```bash
python3 scripts/validate_cases.py /tmp/order-cases.yaml
```

### 5. Run Tests

```bash
python3 scripts/run_tests.py /tmp/order-cases.yaml \
  --env-file /tmp/env.yaml \
  --report /tmp/order-report.json
```

### 6. Analyze Failures

```bash
python3 scripts/analyze_failures.py /tmp/order-report.json \
  --context-json /tmp/order-context.json \
  --output /tmp/order-failure-analysis.json
```

The analyzer prints Chinese output and writes JSON containing:

- `classification`
- `classification_zh`
- `reason_zh`
- `suggestion_zh`
- `source_context`
- `context_evidence`

### 7. Export Agentic QA Gate Evidence

If the API run needs to be attached to Agentic QA Gate, export the normalized automation evidence:

```bash
python3 scripts/export_automation_results.py /tmp/order-report.json \
  --analysis /tmp/order-failure-analysis.json \
  --output /tmp/automation_results.json \
  --run-id order_api_validation_2026_06_01
```

Or generate it directly when executing tests:

```bash
python3 scripts/run_tests.py /tmp/order-cases.yaml \
  --env-file /tmp/env.yaml \
  --report /tmp/order-report.json \
  --automation-results /tmp/automation_results.json
```

The output follows the Agentic QA Gate schema:

- `schema_version`
- `run_id`
- `source_tool`
- `risk_domains`
- `suites`
- `passed_cases`
- `failed_cases`
- `skipped_cases`

## YAML Example

```yaml
metadata:
  api: "POST /api/v1/orders"
  language: "java"
  framework: "spring-boot"
  dimensions_covered:
    - functional_positive

env:
  base_url: "{{ENV.API_BASE}}"
  auth_token: "{{ENV.AUTH_TOKEN}}"

setup:
  - id: create_product
    action: http
    request:
      method: POST
      url: "{{env.base_url}}/api/v1/products"
      params:
        source: "api-test"
      headers:
        Authorization: "Bearer {{env.auth_token}}"
      body:
        name: "测试商品"
    expect:
      status: 201
      body:
        data.id: "@notNull"
    extract:
      productId: "$.data.id"

cases:
  - id: "TC-FUNC-001"
    name: "正常创建订单"
    dimension: functional_positive
    priority: P0
    source: "/path/to/OrderController.java:45"
    request:
      method: POST
      url: "{{env.base_url}}/api/v1/orders"
      headers:
        Authorization: "Bearer {{env.auth_token}}"
      body:
        productId: "{{productId}}"
        quantity: 1
    expect:
      status: 200
      response_time_ms_lt: 1000
      body:
        data.orderId: "@notNull"
    extract:
      orderId: "$.data.orderId"
    teardown:
      - action: http
        request:
          method: DELETE
          url: "{{env.base_url}}/api/v1/orders/{{orderId}}"
          headers:
            Authorization: "Bearer {{env.auth_token}}"
```

## Test Dimensions

| Dimension | Status |
|---|---|
| `functional_positive` | Executable |
| `functional_negative` | Executable |
| `boundary_value` | Executable |
| `security_auth` | Executable |
| `security_injection` | Executable |
| `idempotency` | Executable with `repeat` |
| `state_machine` | Executable |
| `concurrency` | Not executable yet; mark skipped in coverage matrix |
| `data_consistency` | HTTP-observable checks only |
| `compliance` | Executable |

## Development Checks

Run the regression suite:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/pycache-ai-api-tester \
  python3 -m unittest \
  tests.test_route_extractor \
  tests.test_source_analyzer \
  tests.test_schema \
  tests.test_engine \
  tests.test_failure_analyzer \
  tests.test_automation_evidence \
  tests.test_cli_workflow \
  tests.test_skill_install_smoke \
  tests.test_skill_structure -v
```

The suite covers route extraction, source analysis, YAML schema validation, the HTTP runner, failure classification, Agentic QA Gate evidence export, the main CLI workflow, skill structure, and copied-skill smoke behavior.

Validate the skill:

```bash
python3 /Users/ruyi/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill
```

Validate the demo YAML:

```bash
python3 skill/scripts/validate_cases.py examples/demo-order-create.yaml
python3 skill/scripts/validate_cases.py examples/finance-refund-retry.yaml
```

The finance refund retry example is designed for Agentic QA Gate demos. It covers auth boundary, refund limit, external gateway failure consistency, idempotency, and audit evidence. The regression test `tests.test_finance_refund_example` runs it against a local mock HTTP service and verifies that `automation_results.json` marks the idempotency case as `probable_bug`.

## Current Limits

- Route constants and advanced annotation composition are not fully resolved.
- FastAPI router registration across files is only partially supported.
- Java call-chain tracing is heuristic and not fully method-scoped.
- `concurrency` test execution is intentionally disabled for now.
- Database assertions, mocks, file uploads, cookies, and form bodies are not implemented yet.
- Failure analysis is a first-pass classifier; inspect `source_context` and `test_basis` before making final bug claims.

## Repository Notes

This directory is not currently initialized as a Git repository. Before publishing to GitHub, exclude generated files such as `.DS_Store`, `dist/`, `*.egg-info/`, `__pycache__/`, and temporary reports.
