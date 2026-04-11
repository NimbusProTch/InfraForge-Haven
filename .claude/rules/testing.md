---
paths:
  - "api/**"
  - "ui/**"
---

# Testing Rules (Non-Negotiable)

No code change may be committed without tests.

## Why?
This platform serves 342 Dutch municipalities. A bug without test coverage
could affect all tenants simultaneously. Tests are the safety net.

## Workflow
1. Make the code change
2. Verify existing tests still pass
3. Write NEW tests for the change (test count must increase)
4. Include test count in commit message: "Tests: 1185 → 1192 (+7)"

## Test Locations
- Backend tests: `api/tests/test_{module}.py`
- Frontend tests: `ui/__tests__/` or co-located with components
- Playwright E2E: `tests/`
- Run backend: `cd api && pytest tests/ -q`
- Run lint: `cd api && ruff check . && ruff format --check .`

## Forbidden
- Committing without new tests
- Opening a PR without test count in description
- Saying "sprint done" without test count increase
- Saying "tests later" — tests are written NOW
