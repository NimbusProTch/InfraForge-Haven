# Production Environment (Phase 2+)

> **Status:** Skeleton only. Not yet deployable.

This directory will hold the OpenTofu configuration for the production
Haven cluster on **Cyso Cloud / Leafcloud Amsterdam** (EU data sovereignty
for Dutch municipalities). It mirrors `environments/dev/` in structure
but targets OpenStack instead of Hetzner Cloud.

## Why this is empty today

Sprint H0 / H1 are focused on stabilising the dev cluster on Hetzner.
Production rollout is **Phase 2+** in the roadmap and depends on:

- **Sprint H1a**: real Multi-AZ (Falkenstein + Nuremberg, currently Helsinki + Nuremberg by tfvars typo)
- **Sprint H1a**: kubectl OIDC actually working (currently broken)
- **Sprint H1b**: remote tofu state backend (currently local — would lose state on operator machine death)
- **Sprint H1b**: etcd snapshot schedule + S3 upload (currently zero backups — cluster loss = total data loss)
- **Sprint H1c**: `haven-api` ServiceAccount cluster-admin scope-down (currently any pod compromise = full cluster takeover)
- **Sprint H1d**: PSA `restricted` on tenant namespaces (currently `baseline`)
- **Sprint H1d**: BuildKit gVisor sandbox (currently privileged + root)
- **Sprint H1e**: cert-manager-issued internal TLS (currently `httpx verify=False` for ArgoCD/Harbor/Everest)
- **Production-specific**: a real `openstack-infra` module (currently `.gitkeep` only)
- **Production-specific**: Cyso/Leafcloud project + credentials + quota approval

## What this PR (H1b-1 P4.1) ships

This commit creates the directory + this README + a placeholder
`providers.tf` so the directory is no longer just a `.gitkeep`. It does
NOT make production deployable. That is at least Sprint 2's worth of
work and explicit product/legal decisions about Cyso vs Leafcloud
hosting.

## Files

| File | Purpose |
|---|---|
| `README.md` | This file |
| `providers.tf` | Placeholder OpenStack provider config (commented out) |
| `terraform.tfvars.example` | Template values that morning ops will fill in for the actual production deploy |

## Next steps (Sprint 2+)

1. Decide Cyso vs Leafcloud (product + legal call)
2. Open project + obtain OpenStack auth credentials + quota
3. Implement `infrastructure/modules/openstack-infra/` (currently `.gitkeep`)
4. Copy `environments/dev/main.tf` and adapt:
   - Replace `module.hetzner_infra` with `module.openstack_infra`
   - Replace `location_primary = "nbg1"` / `location_secondary = "fsn1"` with OpenStack region/AZ pair (Amsterdam city + DR site)
   - Adjust node sizes for production workload (currently dev 2 vCPU / 4 GiB)
   - Set `operator_cidrs` to operator VPN CIDRs (NOT 0.0.0.0/0)
5. Provision a separate remote tofu state backend (Cloudflare R2 or off-cluster MinIO)
6. Run through the H1 verification checklist before serving any customer traffic
