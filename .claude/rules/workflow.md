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

## PR Lifecycle (Full Automation)

### Phase 1: Feature Branch
1. Create branch from main: `feature/{sprint}-{description}`
2. Write code + tests (per task order above)
3. Push branch, CI runs automatically on self-hosted runner
4. Monitor CI — if fail, fix and re-push until ALL GREEN
5. Create PR with test count in description

### Phase 2: Review
1. Run architect agent — review code, security, architecture
2. Run tester agent — run tests, verify count increased
3. If BLOCKING findings: fix → re-push → re-review
4. Both agents must say APPROVED before proceeding

### Phase 3: Merge to Main
1. Merge PR to main (only after architect + tester APPROVED + CI green)
2. Main branch CI triggers automatically:
   - Lint + Test
   - Docker build (haven-api or haven-ui)
   - Push to Harbor with SHA digest
   - Update deployment manifest with new digest
   - Commit manifest update back to main

### Phase 4: Deploy Verification (after main merge)
1. ArgoCD detects manifest change → syncs automatically
2. Wait for new pod to be Running + Ready:
   ```bash
   KC=infrastructure/environments/dev/kubeconfig
   kubectl --kubeconfig=$KC rollout status deploy/haven-api -n haven-system --timeout=120s
   kubectl --kubeconfig=$KC get pods -n haven-system -l app=haven-api \
     -o jsonpath='{.items[0].spec.containers[0].image}'
   # Image must match the new digest from CI
   ```
3. Verify API/UI accessible:
   ```bash
   curl -s https://api.46.225.42.2.sslip.io/api/docs | head -5
   ```
4. Run full E2E tests including newly added test cases:
   ```bash
   cd api && pytest tests/ -q  # Full backend suite
   npx playwright test          # Full E2E suite
   ```
5. If any step fails → rollback: revert the merge commit

### Phase 5: Post-Deploy
1. Update CLAUDE.md if compliance score changed
2. Update docs/sprints/SPRINT_BACKLOG.md (mark tasks done)
3. Announce completion to user

## PR Rules
- Architect + tester agent review MANDATORY per PR
- Do not open PR without tests
- Do not merge with red CI
- Do not start next sprint with red CI
- After main merge: ALWAYS verify deploy + run E2E
- User must NEVER have to remind these rules — they are automatic
