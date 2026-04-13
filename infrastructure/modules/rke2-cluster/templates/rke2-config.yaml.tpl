token: "${cluster_token}"
%{ if is_first_master ~}
cluster-init: true
%{ else ~}
server: "https://${first_master_private_ip}:9345"
%{ endif ~}
node-ip: "__PRIVATE_IP__"
node-external-ip: "__PUBLIC_IP__"
cni: cilium
disable:
  - rke2-ingress-nginx
tls-san:
  - "${lb_ip}"
  - "${lb_private_ip}"
  - "__PRIVATE_IP__"
  - "__PUBLIC_IP__"
%{ if disable_kube_proxy ~}
disable-kube-proxy: true
%{ endif ~}
%{ if enable_cis_profile ~}
profile: cis
protect-kernel-defaults: true
%{ endif ~}
write-kubeconfig-mode: "0644"
kube-apiserver-arg:
  - "oidc-issuer-url=${keycloak_oidc_issuer_url}"
  - "oidc-client-id=${keycloak_oidc_client_id}"
  - "oidc-username-claim=preferred_username"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-claim=groups"
  - "oidc-groups-prefix=oidc:"
  - "audit-policy-file=/etc/rancher/rke2/audit-policy.yaml"
  - "audit-log-path=/var/log/kube-audit/audit.log"
  - "audit-log-maxage=30"
  - "audit-log-maxbackup=10"
  - "audit-log-maxsize=100"
etcd-snapshot-schedule-cron: "${etcd_snapshot_schedule}"
etcd-snapshot-retention: ${etcd_snapshot_retention}
etcd-snapshot-dir: /var/lib/rancher/rke2/server/db/snapshots
%{ if etcd_s3_enabled ~}
etcd-s3: true
etcd-s3-endpoint: "${etcd_s3_endpoint}"
etcd-s3-bucket: "${etcd_s3_bucket}"
etcd-s3-region: "${etcd_s3_region}"
etcd-s3-access-key: "${etcd_s3_access_key}"
etcd-s3-secret-key: "${etcd_s3_secret_key}"
%{ endif ~}
