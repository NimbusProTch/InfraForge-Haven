#!/usr/bin/env bash
# Seed /etc/hosts on every RKE2 node with static iyziops.com entries.
#
# Why: Hetzner's upstream DNS (185.12.64.1/2) intermittently returns
# SERVFAIL or times out. When a kubelet image pull resolves through
# systemd-resolved's stub (127.0.0.53), a flaky upstream causes
# ErrImagePull with "server misbehaving" / "i/o timeout" errors — even
# though all manifests are valid. A /etc/hosts static entry for
# harbor.iyziops.com short-circuits the resolver before it ever hits
# Hetzner's DNS, so image pulls never depend on the upstream being
# healthy.
#
# This script is idempotent: it only appends the entry if not already
# present. Safe to re-run.
#
# Usage:
#   ./scripts/seed-cluster-dns-hosts.sh
#
# Runs via ProxyJump through the NAT box (cluster nodes have no public
# IPv4). Expects logs/iyziops-prod-ssh.pem to be readable.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$REPO_ROOT/logs/iyziops-prod-ssh.pem"
NAT_IP="46.225.154.1"

# All 6 cluster node private IPs. Update if cluster topology changes.
NODES=(
  10.10.1.10   # iyziops-master-0
  10.10.1.4    # iyziops-master-1
  10.10.1.3    # iyziops-master-2
  10.10.1.5    # iyziops-worker-0
  10.10.1.6    # iyziops-worker-1
  10.10.1.7    # iyziops-worker-2
)

# Resolved once from public DNS (Cloudflare), then written to each node's
# hosts file. If iyziops.com moves off this ingress LB, re-run this script
# to pick up the new IP.
INGRESS_IP=$(dig +short @1.1.1.1 harbor.iyziops.com | head -1)
if [[ -z "$INGRESS_IP" ]]; then
  echo "ERROR: could not resolve harbor.iyziops.com via public DNS" >&2
  exit 1
fi

HOSTS_LINE="$INGRESS_IP harbor.iyziops.com iyziops.com api.iyziops.com keycloak.iyziops.com"

SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
PROXY="ssh ${SSH_OPTS[*]} -W %h:%p root@${NAT_IP}"

echo "==> seeding /etc/hosts with: $HOSTS_LINE"
for ip in "${NODES[@]}"; do
  ssh "${SSH_OPTS[@]}" -o "ProxyCommand=${PROXY}" "root@${ip}" bash -s <<EOF
if grep -q "harbor.iyziops.com" /etc/hosts; then
  echo "  \$(hostname): already present"
else
  echo "${HOSTS_LINE}" >> /etc/hosts
  echo "  \$(hostname): added"
fi
getent hosts harbor.iyziops.com | awk '{ print "    resolves to:", \$1 }'
EOF
done

echo "==> done. All nodes can now resolve harbor.iyziops.com regardless of upstream DNS health."
