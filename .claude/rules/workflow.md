# Sprint & Task Execution Rules

## When Research is Requested ("research", "deep dive", "check", "investigate")
1. **ALWAYS** launch multi-agent (2-3 Explore agents in parallel)
2. Agents must:
   - Agent 1: Read live code line-by-line (file:line references)
   - Agent 2: Research best practices / industry standards
   - Agent 3: Scan for security + structural issues
3. Produce a **live state vs best practice** comparison table
4. Do NOT trust CLAUDE.md claims of "done" — read the actual code
5. "Code ready" ≠ "works correctly" — confirm every claim in the file
6. Find ALL issues on the first pass — user must not have to ask twice
7. Plans are only written AFTER research is complete

## Sprint Task Order (NEVER skip a step)
For each task, in order:
1. Read + modify code
2. **WRITE TESTS** — see rules/testing.md, this step is MANDATORY
3. Lint check (`ruff check . && ruff format --check .`)
4. Commit with test count: "Tests: 1185 → 1192 (+7)"
5. Push + monitor CI (self-hosted runner: [self-hosted, haven])
6. Do NOT proceed to next task until CI is green

## Sprint Completion Checklist
- All tasks + tests completed
- CI ALL GREEN (all workflows)
- PR description includes test count before/after
- Architect agent review done (no blocking bugs)
- Tester agent review done (tests pass, count increased)
- docs/sprints/SPRINT_BACKLOG.md updated

## PR Rules
- Architect + tester agent review MANDATORY per PR
- Do not open PR without tests
- Do not merge with red CI
- Do not start next sprint with red CI
- User must NEVER have to remind these rules — they are automatic
