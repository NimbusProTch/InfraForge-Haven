# IaC Discipline

Rules for OpenTofu / Terraform code in this repo. These exist because the previous `infrastructure/environments/dev/main.tf` grew to 2022 lines of imperative bash-in-HCL — 22 `ssh_resource` blocks, inline `kubectl | curl | heredoc`, hardcoded IPs, fragile destroy ordering. We are not going back there.

These rules apply to every file under `infrastructure/`, `runner/`, and `platform/argocd/appsets/`. They are enforced by the `devops-architect` agent on every change.

## The ten rules

1. **No hardcoded environment values** in `.tf` files. Every env-specific value comes from a variable with a `description` and, where applicable, a `validation` block.

2. **No inline `kubectl`, `curl`, or `heredoc`** in `.tf` files. Post-cluster operations belong in ArgoCD Applications, not in tofu. The exception is `data.http` for readiness probing.

3. **No `helm_release`, `kubernetes_manifest`, or `ssh_resource` in the core backbone.** The iyziops plan is cloud-init + RKE2 Helm Controller + `data.http` only. Helm Controller does installs inside the cluster; cloud-init writes the manifests.

4. **No `local_sensitive_file.kubeconfig`.** Operators pull the kubeconfig via the `make kubeconfig` target (SCP from the first master). Tofu does not manage kubeconfig files.

5. **Module size cap: 200 lines per `.tf` file.** Split if larger. Environment `main.tf` files may be split into logical sections (e.g. `hetzner.tf`, `rke2.tf`, `dns.tf`).

6. **Every module has**: `main.tf`, `variables.tf` with descriptions, `outputs.tf` with descriptions, and `README.md` (purpose, inputs, outputs, example usage).

7. **Every `.tf` file starts with an English header comment** explaining its purpose in two or three lines.

8. **Every change is reviewed by the `devops-architect` agent** before commit and before `tofu apply`.

9. **Secrets never appear in code.** Tokens, passwords, deploy keys come from the macOS Keychain via the `iyziops-env` loader function, exported as `TF_VAR_*` / `AWS_*` environment variables. A literal token or password in a `.tf` file is a hard blocker.

10. **Scratch output goes to `logs/`.** Tofu plan files, apply logs, kubectl dumps, and debug files live in `logs/` at the repo root (gitignored). Never write them into `infrastructure/environments/*/` or `runner/`. See `logs-directory.md`.

## Variables — concrete requirements

- Every `variable` block has a `description`.
- Every `variable` that represents an env-specific value (CIDR, location, size, count) has no `default` — force it to come from tfvars or env vars.
- Variables that accept a CIDR list must validate against `0.0.0.0/0` and `::/0`.
- Sensitive variables are marked `sensitive = true`.

## Providers — allowed set

In the iyziops plan environment (`infrastructure/environments/prod/`):

- `hcloud` (Hetzner Cloud)
- `cloudflare` (DNS)
- `http` (readiness probing via `data.http`)
- `tls` (SSH key generation)
- `random` (cluster token, etc.)
- `local` (rendering SSH key file only)

**Forbidden** in this environment: `helm`, `kubernetes`, `kubernetes-alpha`, `ssh`, `rancher2`.

## Cloud-init

- Helm Controller manifests are written by the **first master only**. Joining masters and workers must not write to `/var/lib/rancher/rke2/server/manifests/`.
- Every `${...}` interpolation in a `.tpl` file must map to a known variable or local. Unresolved placeholders are a blocker.
- Secret material in `user_data` is acceptable (Hetzner API exposes it at the same trust level as tfvars), but must not leak into a non-sensitive output.

## Backend

- Remote state only. Hetzner Object Storage S3 buckets with versioning on.
- `use_lockfile = true` (OpenTofu 1.10+ native S3 locking).
- Separate bucket per environment: `iyziops-tfstate-prod`, `iyziops-tfstate-runner`.

## Destroy ordering

- `tofu destroy` must complete in a single run with zero orphans.
- No `depends_on` chains that rely on K8s API being up during destroy.
- When in doubt, run a destroy test after every major change.

## On commit

The commit message for an infrastructure change should include a one-line summary of which rule the change affects and whether the devops-architect agent approved. Example:

```
infra(rke2-cluster): add Longhorn HelmChart manifest template

DevOps Architect: APPROVED
Rule 3 applies (no helm_release, using Helm Controller).
```
