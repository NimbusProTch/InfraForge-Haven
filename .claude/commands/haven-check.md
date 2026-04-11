# /haven-check — Haven 15/15 Compliance Verification

Verify Haven compliance score against live code and (if accessible) kubectl.

## Verification Steps

1. **Code verification** (always):
   - Read relevant files (main.tf, variables.tf, helm-values/, manifests/)
   - Are variables correctly set?
   - Do templates render correctly?
   - Any hardcoded bugs?

2. **Cluster verification** (if kubeconfig available):
   ```bash
   KC=infrastructure/environments/dev/kubeconfig
   kubectl --kubeconfig=$KC get nodes -L topology.kubernetes.io/zone  # Check 1
   kubectl --kubeconfig=$KC get nodes                                 # Check 2
   kubectl --kubeconfig=$KC version                                   # Check 3
   # ... all 15 checks
   ```

3. **Report:**
   - Score: X/15
   - Each item: PASS / CODE READY / BROKEN
   - Broken items: what's wrong, how to fix
   - Compare with previous score

## Rules
- Do NOT trust CLAUDE.md score — read code, check cluster
- Clearly separate "code ready" from "live and working"
- Provide source file + line number for each check
