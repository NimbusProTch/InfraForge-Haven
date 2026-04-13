token: "${cluster_token}"
server: "https://${first_master_private_ip}:9345"
node-ip: "__PRIVATE_IP__"
node-external-ip: "__PUBLIC_IP__"
# cloud-provider=external: workers also wait for Hetzner CCM to initialize
# them. CCM tolerates the uninitialized taint so it schedules in time.
kubelet-arg:
  - "cloud-provider=external"
%{ if enable_cis_profile ~}
profile: cis
protect-kernel-defaults: true
%{ endif ~}
