# Context JSON Format

`scripts/gen_context.py` writes a JSON file used to generate source-backed test cases.

## Top-Level Fields

```json
{
  "project": {},
  "api": {},
  "test_basis": {},
  "code_files": [],
  "risk": {},
  "schema_constraints": []
}
```

## `test_basis`

Use `test_basis` as the primary source for generating cases. Use `code_files` when a detail is missing or needs confirmation.

| Field | Meaning |
|---|---|
| `route` | Matched route method, path, file, line, and handler. |
| `request_models` | Request DTO/Pydantic model names and source locations. |
| `fields` | Request/model fields with type, required flag, constraints, and source. |
| `auth` | Authentication/authorization evidence. |
| `branches` | Branches and exceptions useful for negative/domain cases. |
| `state_changes` | Status/state assignments or transition hints. |
| `external_calls` | HTTP/SDK/external dependency call hints. |
| `sensitive_fields` | Sensitive field hints for compliance cases. |

## Generation Guidance

- Prefer `test_basis.fields` for functional negative and boundary cases.
- Prefer `test_basis.auth` for `security_auth`.
- Prefer `test_basis.branches` for domain rule and error path cases.
- Prefer `test_basis.state_changes` for `state_machine`.
- Prefer `test_basis.external_calls` for partial failure and data consistency ideas, but only generate HTTP-observable checks.
- Prefer `test_basis.sensitive_fields` for compliance and masking checks.
- Every case `source` should come from a `source` field in `test_basis` or a verified line in `code_files`.

## Known Limits

- Static analysis is heuristic. Confirm important assumptions by reading `code_files`.
- FastAPI router registrations imported from other files are not fully resolved yet.
- Java route constants and advanced annotation composition are not fully resolved yet.
- Branch extraction is file-level, not always method-scoped.
