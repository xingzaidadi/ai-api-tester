# Assertion Syntax

Smart assertions are string values beginning with `@`. They are valid in `expect.body` and `expect.headers`.

## Status And Response Time

```yaml
expect:
  status: 200
  response_time_ms_lt: 1000
```

`status` may be an integer or a smart assertion such as `@in([200,400])`.

## Value Assertions

| Assertion | Meaning | Example |
|---|---|---|
| `@notNull` | Value is not null | `data.id: "@notNull"` |
| `@isNull` | Value is null | `data.deletedAt: "@isNull"` |
| `@notEqual(V)` | Value is not equal to V after string conversion | `code: "@notEqual('0')"` |
| `@in([...])` | Value is in JSON list | `data.status: "@in([\"PENDING\",\"PAID\"])"` |

## Numeric Assertions

| Assertion | Meaning | Example |
|---|---|---|
| `@gt(N)` | Greater than N | `data.total: "@gt(0)"` |
| `@gte(N)` | Greater than or equal to N | `data.count: "@gte(1)"` |
| `@lt(N)` | Less than N | `data.discount: "@lt(1)"` |
| `@lte(N)` | Less than or equal to N | `data.rate: "@lte(100)"` |

## String Assertions

| Assertion | Meaning | Example |
|---|---|---|
| `@contains('S')` | Contains substring | `message: "@contains('success')"` |
| `@not_contains('S')` | Does not contain substring | `message: "@not_contains('exception')"` |
| `@matches(regex)` | Regex match | `phone: "@matches(\\d{3}\\*{4}\\d{4})"` |
| `@startsWith('S')` | Starts with substring | `orderNo: "@startsWith('ORD')"` |
| `@endsWith('S')` | Ends with substring | `file: "@endsWith('.pdf')"` |

## Collection Assertions

| Assertion | Meaning | Example |
|---|---|---|
| `@size(N)` | Exact length | `items: "@size(3)"` |
| `@minSize(N)` | Minimum length | `items: "@minSize(1)"` |
| `@maxSize(N)` | Maximum length | `items: "@maxSize(100)"` |

## Type Assertions

| Assertion | Meaning | Example |
|---|---|---|
| `@isString` | Value is a string | `name: "@isString"` |
| `@isNumber` | Value is an integer or float | `amount: "@isNumber"` |
| `@isArray` | Value is an array/list | `items: "@isArray"` |

## Body-Level Assertions

Only `@not_contains` is supported as a body-level assertion key:

```yaml
expect:
  body:
    "@not_contains": ["error", "sql", "exception", "stack trace"]
```
