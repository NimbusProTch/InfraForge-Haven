# Haven 15/15 — Roadmap

**STATUS: IMPLEMENTATION COMPLETE 2026-04-14** — see `docs/sprints/HAVEN_15_15_SPRINT_20260414.md` for the sprint summary. Pending `tofu apply` + `make haven` verification (Phase D/E).

Previous score (2026-04-13): **13/15 PASS**.

Two remaining failures, both infrastructure-level. Neither can be fixed from inside the cluster — both require tofu apply cycles. Both are non-trivial: they need planning, staging, and an operator-assisted cutover.

## Check #1 — Multiple availability zones in use

### Why it fails today

The iyziops-prod environment deploys all 6 RKE2 nodes (3 masters + 3 workers) into `fsn1-dc14` Hetzner datacenter in a single Hetzner location. Haven CLI `check` walks every node's `topology.kubernetes.io/zone` label and requires at least 2 distinct values. Ours is `fsn1-dc14` everywhere.

Current tfvars:
```hcl
location           = "fsn1"   # Falkenstein
datacenter         = "fsn1-dc14"
# (no secondary, no fallback)
```

### What the fix looks like

Hetzner Cloud has three continental-EU datacenters that satisfy Haven's "multiple availability zones" definition when used in combination:
- `fsn1-dc14` — Falkenstein (Germany)
- `nbg1-dc3` — Nuremberg (Germany)
- `hel1-dc2` — Helsinki (Finland)

All three sit inside the same `eu-central` Hetzner Cloud network region so a single Hetzner Network (RFC1918 range) can span them. Inter-DC latency: ~15 ms Fsn↔Nbg, ~25 ms Fsn↔Hel. Both are acceptable for RKE2 etcd and for Longhorn synchronous replication.

The clean implementation shape:

1. **Variables** — add to `infrastructure/environments/prod/variables.tf`:
   ```hcl
   variable "locations" {
     type    = list(string)
     default = ["fsn1", "nbg1", "hel1"]
   }
   ```
2. **Node distribution** — stripe `var.master_count` and `var.worker_count` across `var.locations` in `infrastructure/modules/hetzner-infra/main.tf`:
   ```hcl
   resource "hcloud_server" "master" {
     count      = var.master_count
     name       = "iyziops-master-${count.index}"
     location   = element(var.locations, count.index)
     ...
   }
   ```
3. **Label propagation** — cloud-init writes `node-label: topology.kubernetes.io/zone=<location>` into `/etc/rancher/rke2/config.yaml` so kubelet publishes the label to the apiserver. RKE2 respects node-label for all non-reserved keys.
4. **LB reachability** — the existing Hetzner Load Balancer (iyziops-prod-ingress + iyziops-prod-api) already lives at network-region level, not DC level, so both LBs already target nodes in any DC inside the same network region. No LB changes needed.
5. **Longhorn replicaCount adjustment** — increase `defaultReplicaCount` from 3 to match the number of locations so every volume has a replica in each DC; OR keep at 3 but pin affinity to ensure cross-DC distribution via `diskSoftAntiAffinity: true` (already on). The existing 3 replicas are enough — the anti-affinity will place them across DCs automatically once nodes carry the zone label.
6. **Tofu apply** with `-parallelism=1` on server resources to avoid Hetzner API rate limiting during the 6-node rebuild.

### Risks
- **Downtime** — the whole cluster is destroyed and rebuilt (~15 minutes hands-off per the previous destroy+apply tests). Not a problem for iyziops-dev but blocks any tenant traffic mid-cutover.
- **Longhorn replica re-balancing after reboot** — Longhorn needs ~10 minutes per volume to rebuild replicas on new DCs. During that window volumes stay Healthy but I/O is slower.
- **etcd cross-DC quorum latency** — ~15 ms Fsn↔Nbg is fine for etcd; ~25 ms Fsn↔Hel is borderline. If etcd complains (elections flapping), drop Hel and keep Fsn+Nbg only.

### Effort
- Code: 1–2 hours (tofu module edits + tfvars + cloud-init templatefile variable wiring).
- Apply: 60–90 minutes including replica rebalance.
- Verification: `kubectl get nodes -L topology.kubernetes.io/zone` → 3 distinct values. `make haven` → multiaz: YES.

### Execution slice
**Operator task** (cannot be automated in a long-running overnight session because it requires the operator to physically watch the rebuild):
```
tofu -chdir=infrastructure/environments/prod plan -var-file=prod.auto.tfvars -out=/tmp/multiaz.tfplan
tofu -chdir=infrastructure/environments/prod apply /tmp/multiaz.tfplan
make kubeconfig
kubectl get nodes -L topology.kubernetes.io/zone
make haven
```

---

## Check #2 — Private networking topology

### Why it fails today

Haven CLI's `privatenetworking` check inspects each node's `InternalIP` (the address RKE2 uses for kubelet↔apiserver and for node-to-node traffic) and fails if any of them is a globally-routable public IPv4. Ours are Hetzner public IPs.

Root cause: the RKE2 nodes currently register with `--node-ip=<public_ipv4>` (the default when `--node-ip` is omitted). This was a legacy decision because the original cluster didn't use a Hetzner private network — inter-node traffic crossed the public internet (firewalled).

Current state:
- Nodes DO have Hetzner private IPs already (we provisioned `hcloud_network` with `10.0.0.0/16` in `infrastructure/modules/hetzner-infra/hetzner.tf`).
- But kubelet is not using them. `kubectl get nodes -o wide` shows public IPs in the `INTERNAL-IP` column.

### What the fix looks like

1. **Cloud-init change** — inject the private IP into kubelet at register time:
   ```yaml
   # infrastructure/modules/rke2-cluster/templates/node-cloud-init.yaml.tpl
   write_files:
     - path: /etc/rancher/rke2/config.yaml
       content: |
         node-ip: "__PRIVATE_IP__"
         node-external-ip: "__PUBLIC_IP__"
         ...
   ```
   `__PRIVATE_IP__` comes from the Hetzner metadata API or from a cloud-init template variable (`hcloud_server.master[*].network[0].ip`).
2. **Tofu wiring** — `templatefile()` in `infrastructure/environments/prod/rke2.tf` needs to pass each node's private IP into its individual cloud-init render.
3. **Firewall lockdown** — once all traffic uses private IPs, tighten `hcloud_firewall.iyziops_nodes` to block 6443/2379/2380/10250 on public IPs entirely (private network default-allow). This is the bonus payoff: closing publicly-exposed kube-apiserver and etcd ports.
4. **LB → node target mode** — the Hetzner Load Balancer already uses `use_private_ip = true` per the iyziops-gateway annotation so external 80/443 ingress still works after the lockdown. API LB (6443) also needs `use_private_ip = true`.
5. **kubeconfig update** — operator kubeconfig still points at the public API LB IP (142.132.240.246). Keep this — the API LB stays reachable from outside. Only the inter-node plane goes private.

### Risks
- **Cluster rebuild required.** `--node-ip` is set at kubelet register time; changing it on an existing node means unjoining + rejoining, which is the same as rebuild. So this fix has to ride the same tofu apply cycle as multiaz.
- **Hetzner Private Network MTU** — default is 1400, RKE2 + Cilium default MTU is 1500. If we don't override Cilium MTU we'll get path-MTU issues manifesting as stuck connections. Fix: `cilium.tunnel-mtu: 1450` in `cilium-values.yaml.tpl` (already have a templatefile slot).
- **Longhorn CSI socket** — Longhorn uses node IPs for socket paths; changing node IPs triggers volume re-attach. Plan for 5–10 minutes of volume unavailability per node during the cutover.

### Effort
- Code: 2–3 hours (cloud-init template variable plumbing + MTU tune + firewall lockdown).
- Apply: shares the 60–90 minute multiaz window (same rebuild).
- Verification: `kubectl get nodes -o wide | awk '{print $6}'` → all 10.0.x.x. `make haven` → privatenetworking: YES.

### Execution slice
Bundle this with multiaz — same rebuild, one tofu apply. The combined change gets both checks green in a single operator intervention.

---

## Combined sprint: Haven 15/15 in one shot

```
Day 1 (planning, 2h)    : write the multi-location + private-ip patches on a branch
Day 1 (review, 1h)      : devops-architect agent review, dry-run plan
Day 1 (stage, 30m)      : backup tag, destroy the current iyziops-dev cluster
Day 1 (apply, 90m)      : tofu apply hands-off, measure boot time
Day 1 (verify, 30m)     : kubectl checks, make haven, full app restore
```

Total: ~5–6 hours operator-attended, in a single maintenance window.

---

## Other small wins (not required for 15/15 but worth bundling)

1. **cert-manager wildcard cert refresh test.** After the multi-DC rebuild, proactively kill the cert and force a new issuance so we catch any DNS-01 cleanup races early. Already a known pre-existing issue (CLAUDE.md gotcha).
2. **MinIO/Grafana/Harbor password rotation via Vault ExternalSecret.** Phase 3 proved the round-trip. Writing the three ExternalSecret manifests + rotating the source secrets is ~30 minutes.
3. **Harbor registry blob storage → MinIO S3 backend.** Chart supports this via `imageChartStorage.type: s3` + `existingSecret`. Needs an ExternalSecret holding `accesskey` + `secretkey`. Unblocks cross-DC blob replication via Longhorn on MinIO's 50Gi PVC.
4. **Private-networking bonus: drop NodePort 30000–32767 from firewall entirely.** Already closed in the current firewall; just remove the explicit NodePort allow blocks to shave a few rules.

---

## Honest limits

- **This cluster cannot go 15/15 via any automation.** Both remaining failures are tofu-apply + rebuild operations. They need an operator to watch and verify.
- **There is no cluster-side workaround for either check.** The Haven CLI inspects node labels and IPs directly from kube-apiserver; no admission webhook or Kyverno rule can fake compliance.
- **Multi-region Leafcloud / Cyso Cloud migration** (Phase 2+ of the original roadmap) automatically satisfies multiaz because those clouds expose real multi-AZ topology. That migration is out of scope for iyziops-dev; when it happens, both checks will pass organically without any iyziops-specific code.
