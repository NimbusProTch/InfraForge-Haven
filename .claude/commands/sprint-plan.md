# /sprint-plan — Create Sprint Plan

Create a sprint plan ONLY AFTER deep-dive research is complete.

## Prerequisite
This command should ONLY run after a deep-dive. If no research was done in this conversation, run /deep-dive first.

## Flow

1. **Gather deep-dive findings:**
   - Summarize research results from this conversation
   - List critical issues, gaps, best practice differences

2. **Split into sprints:**
   - Each sprint max 2-3 days
   - Priority: CRITICAL → HIGH → MEDIUM
   - Dependency order: infra → backend → frontend
   - Each sprint must have verifiable output

3. **For each sprint:**
   - Task list (checkbox format)
   - Files to modify (full paths)
   - New files to create
   - Test plan (what to test, how)
   - Definition of Done

4. **Save to plan file:**
   - Write to `docs/sprints/` as markdown

## Rules
- No plan without deep-dive — user doesn't want surface-level plans
- Each task must have file path + what changes
- Vague tasks like "do X" forbidden — be specific: "change main.tf:252 from Y to Z"
- No sprint plan without test plan
- Must follow CLAUDE.md Definition of Done
