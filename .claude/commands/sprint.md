# /sprint — Sprint Execution Checklist

Mandatory checklist for every sprint task. Skipping steps is forbidden.

## Per Task (in order)

### 1. Write Code
- [ ] Read existing code (file + line number)
- [ ] Make the change
- [ ] Lint: `ruff check . && ruff format --check .` (Python) or `npm run lint` (UI)

### 2. Write Tests (MANDATORY — DO NOT SKIP)
- [ ] Find existing related tests (`grep -r "test.*{function}" api/tests/`)
- [ ] Write new tests proving the change works
- [ ] Test must FAIL without the change, PASS with it
- [ ] Test count must increase

### 3. Run Tests
- [ ] `pytest tests/ -q` — all tests pass
- [ ] New tests pass
- [ ] Existing tests not broken

### 4. Commit
- [ ] Message includes: what changed + which tests added
- [ ] Test count: "Tests: 1185 → 1192 (+7)"

### 5. Push + CI
- [ ] Push to remote
- [ ] Monitor CI — ALL GREEN required
- [ ] If fail → fix → push again

## Sprint End
- [ ] All tasks completed with tests
- [ ] CI ALL GREEN
- [ ] PR description has test count
- [ ] Architect agent: APPROVED
- [ ] Tester agent: APPROVED

## Rules
- No commit without tests
- No PR without tests
- No "sprint done" without test count increase
- No next sprint while CI is red
- User must NEVER have to remind these — automatic enforcement
