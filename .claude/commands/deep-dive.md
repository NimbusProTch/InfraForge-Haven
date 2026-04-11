# /deep-dive — Multi-Agent Deep Dive Research

User wants a topic researched. NEVER write a surface-level plan. Understand the real state first.

## Mandatory Flow

1. **Launch 3 Explore agents in parallel:**
   - Agent 1: Read live code line-by-line (file paths + line numbers)
   - Agent 2: Research best practices / industry standards
   - Agent 3: Scan for security + structural issues

2. **Produce Gap Analysis Report:**
   - Live state vs Best practice comparison table
   - All issues with severity: CRITICAL / HIGH / MEDIUM / LOW
   - Each issue: file path, line number, what's wrong, what it should be
   - Actionable recommendations

3. **Rules:**
   - Do NOT trust CLAUDE.md "done" claims — read actual code
   - "Code ready" ≠ "works correctly" — confirm in file
   - Find ALL issues first pass — user must NOT ask twice
   - Report must be clear and scannable

4. **NEVER write a plan at this stage.** Research report only.

## Usage
```
/deep-dive kyverno multi-tenancy
/deep-dive infra haven compliance
```
