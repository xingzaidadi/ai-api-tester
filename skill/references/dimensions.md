# Testing Dimensions

Generate only dimensions that apply to the located source code. Explain skipped dimensions in the coverage matrix.

| # | Dimension | ID | Priority | When to Apply | Min Cases | Runner Status |
|---|---|---|---|---|---:|---|
| 1 | Functional Positive | `functional_positive` | P0 | Always | 1-3 | Executable |
| 2 | Functional Negative | `functional_negative` | P1 | Required fields, invalid types, missing params | 2-5 | Executable |
| 3 | Boundary Value | `boundary_value` | P1 | Numeric, length, enum, regex, precision constraints | 1-4 | Executable |
| 4 | Security Auth | `security_auth` | P0 | Auth/role/ownership rules exist | 1-4 | Executable |
| 5 | Security Injection | `security_injection` | P1 | External input fields exist | 1-3 | Executable |
| 6 | Idempotency | `idempotency` | P1 | POST/PUT or unique constraints exist | 1-2 | Executable with `repeat` |
| 7 | State Machine | `state_machine` | P0 | Status fields or transition methods exist | 1-4 | Executable |
| 8 | Concurrency | `concurrency` | P1 | Shared stock/balance/quota deduction exists | 0 | Skip for now |
| 9 | Data Consistency | `data_consistency` | P1 | Multi-table writes or transactional boundaries exist | 1-2 | Executable only as HTTP-observable checks |
| 10 | Compliance | `compliance` | P2 | Sensitive fields or error responses exist | 1-2 | Executable |

## Evidence Sources

Use only evidence found in source files or generated context:

- Request validation: `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Max`, `@Pattern`, Pydantic `Field`, Go binding tags.
- Branches: `if`, `switch`, `case`, early returns, raised exceptions.
- Auth: `@PreAuthorize`, `@Secured`, security config, JWT filters, FastAPI `Depends`, middleware.
- Persistence: repositories, mappers, SQL/XML mappers, ORM model constraints.
- State: enum status fields, `setStatus`, assignment to `status`, transition methods.
- External calls: Feign, RestTemplate, HTTP clients, SDK calls.
- Sensitive fields: phone, mobile, email, idCard, bankCard, address, token.

## Dimension Rules

- `functional_positive`: cover the main successful path and important alternate valid branches.
- `functional_negative`: cover missing required fields, invalid types, nonexistent resources, and domain rule violations.
- `boundary_value`: test min-1/min/max/max+1 for numeric or length constraints.
- `security_auth`: include no token, invalid token, wrong role, and ownership checks when source evidence exists.
- `security_injection`: use SQL/XSS/SSRF payloads only on fields that flow to query, HTML, URL, or external calls.
- `idempotency`: use `repeat` and `expect.all_responses_identical` when repeated requests should be stable.
- `state_machine`: test legal and illegal status transitions.
- `concurrency`: do not generate executable cases yet. Mark skipped with reason: current runner does not execute concurrent requests.
- `data_consistency`: only generate HTTP-observable checks. Do not write database assertions until runner support exists.
- `compliance`: verify masking and absence of stack traces or internal exception names.
