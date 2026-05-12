# Failure Analysis

Use `scripts/analyze_failures.py` after `scripts/run_tests.py` writes a JSON report.

```bash
python3 scripts/analyze_failures.py reports/result.json \
  --context-json tests/order_context.json \
  --output reports/failure-analysis.json
```

`--context-json` is optional. When provided, the analyzer uses `test_basis` evidence to refine suggestions.

## Classification Types

| Type | Meaning |
|---|---|
| `env_issue` | Environment, credentials, base URL, unresolved variables, or network/service availability problem. |
| `test_issue` | Test data, setup, extracted variable, expected JSON path, or expected contract likely needs correction. |
| `probable_bug` | The API likely violates source intent, validation rules, auth/security behavior, state rules, or returns server errors. |

## Heuristics

- Unresolved `{{...}}` variables -> `env_issue`.
- Connection errors, DNS failures, refused connections, and timeouts -> `env_issue`.
- Setup 401/403 -> `env_issue`.
- Case 401/403 outside `security_auth` -> `env_issue`.
- Missing response path such as `expected not null, got None` -> `test_issue`.
- HTTP 5xx -> `probable_bug`.
- Failed `security_auth`, `security_injection`, or `compliance` cases -> `probable_bug`.
- Failed `boundary_value`, `functional_negative`, `state_machine`, `idempotency`, or `data_consistency` cases -> `probable_bug` when the expectation matches source evidence.
- Teardown errors after a passing case -> `test_issue`.

## Output Use

The analyzer outputs Chinese console text and JSON with both machine-readable English fields and Chinese display fields:

- `classification`: `env_issue` / `test_issue` / `probable_bug`
- `classification_zh`: Chinese label
- `reason` and `reason_zh`
- `suggestion` and `suggestion_zh`
- `source_context`: source snippet around `source` when the file exists locally
- `context_evidence`: selected `test_basis` evidence when `--context-json` is provided

Treat the analyzer result as a first pass. For every `probable_bug`, read `source_context`, the case `source`, and relevant `test_basis` before giving a final fix recommendation.
