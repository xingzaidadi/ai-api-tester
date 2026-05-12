# YAML Test Case Format

Use only fields supported by `scripts/validate_cases.py` and `scripts/run_tests.py`.

## Top-Level Structure

```yaml
metadata:
  api: "POST /api/v1/orders"
  language: "java"
  framework: "spring-boot"
  generated_at: "2026-05-10T10:00:00"
  risk_score: 7.5
  dimensions_covered:
    - functional_positive
    - functional_negative

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
    source: "src/main/java/com/example/OrderController.java:45"
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

## Supported Fields

| Path | Required | Notes |
|---|---:|---|
| `metadata.api` | Yes | Human-readable method and path. |
| `metadata.dimensions_covered` | No | List of generated dimensions. |
| `env` | No | Key-value variables. Values may reference `{{ENV.KEY}}`. |
| `setup[].id` | Yes | Unique setup step ID. |
| `setup[].action` | No | Only `http` is supported. |
| `setup[].request` | Yes | Same request shape as cases. |
| `setup[].expect` | No | Optional setup assertions. If omitted, setup fails on HTTP status >= 400. |
| `setup[].extract` | No | Map variable names to JSON paths starting with `$.`. |
| `cases[].id` | Yes | Unique case ID. |
| `cases[].name` | Yes | Chinese case name. |
| `cases[].dimension` | Yes | One supported dimension ID. |
| `cases[].priority` | Yes | `P0`, `P1`, or `P2`. |
| `cases[].source` | Yes | File and line/code source for the test case. |
| `cases[].request` | Yes | HTTP request. |
| `cases[].expect` | Yes | Assertions. Must include `status`. |
| `cases[].extract` | No | Extract variables from the case response. |
| `cases[].teardown` | No | HTTP cleanup steps. |
| `cases[].repeat` | No | Positive integer for repeat/idempotency tests. |

## Request Fields

Only these request fields are supported:

```yaml
request:
  method: POST
  url: "{{env.base_url}}/path"
  params:
    page: 1
  headers:
    Header-Name: "value"
  body:
    field: value
  timeout: 30
```

Supported methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`.

Use `params` for query string parameters. `query` is accepted as an alias, but do not include both in the same request.

## Expect Fields

```yaml
expect:
  status: 200
  response_time_ms_lt: 1000
  all_responses_identical: true
  body:
    data.id: "@notNull"
  headers:
    Content-Type: "@contains('application/json')"
```

`status` is required for every case. `setup[].expect.status` is optional. `all_responses_identical` is useful with `repeat`.

## Report Fields

JSON reports include request/response details for failure analysis:

- `request`: resolved method, URL, headers, params, body, and timeout.
- `response_status`
- `response_headers`
- `response_body`
- `extracted_variables`
- `teardown_errors`

## Variables

| Syntax | Source | Example |
|---|---|---|
| `{{ENV.KEY}}` | System environment variable or env file key named `KEY` | `{{ENV.API_BASE}}` |
| `{{env.key}}` | YAML `env` section after resolution | `{{env.base_url}}` |
| `{{setup.stepId.var}}` | Setup extraction | `{{setup.create_product.productId}}` |
| `{{case.caseId.var}}` | Case extraction | `{{case.TC-FUNC-001.orderId}}` |
| `{{varName}}` | Runtime variable from setup/case extraction | `{{orderId}}` |
| `{{data.id}}` | Last response path compatibility | `{{data.orderId}}` |

## Unsupported Fields

Do not generate these fields until runner support is added:

- `concurrent`
- `precondition`
- database assertions
- mock definitions
- assertions not listed in `references/assertions.md`
