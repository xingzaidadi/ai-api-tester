# Routing Support

Route lookup first uses `scripts/ai_api_tester/route_extractor.py`. If no route matches, `locate.py` falls back to text search.

## Spring Boot

Supported:

- Class-level `@RequestMapping("/prefix")`.
- Method-level `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`.
- `@RequestMapping(value = "/path", method = RequestMethod.POST)`.
- Path parameters such as `/orders/{orderId}`.
- Matching concrete URLs such as `/orders/123` against parameterized routes.

Known limits:

- Complex constants in route annotations are not resolved.
- Multi-controller inheritance and meta-annotations are not resolved.
- Call-chain tracing is heuristic and may include related DTO/service files from the whole controller.

## FastAPI

Supported:

- `APIRouter(prefix="/orders")`.
- `app.include_router(router, prefix="/api/v1")` when declared in the same file.
- Decorators such as `@router.post("")`, `@router.get("/{id}")`, and `@app.get("/health")`.
- Matching concrete URLs against `{param}` routes.

Known limits:

- Router prefixes imported from another file are not resolved yet.
- Constants used as path strings are not resolved.
- Dependency and Pydantic model extraction is still handled by later context analysis, not route extraction.
