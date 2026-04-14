#cloud-config
# =============================================================================
#  iyziops — NAT box cloud-init
# =============================================================================
#  Enables kernel IP forwarding and installs a single iptables MASQUERADE
#  rule that rewrites any packet leaving the private subnet. Persistence is
#  handled by a systemd oneshot unit that re-applies the rule on boot, so
#  there is no dependency on iptables-persistent or apt install.
#
#  The NAT box is the only cluster node with public IPv4. Cluster masters
#  and workers have public_net.ipv4_enabled=false (Haven privatenetworking)
#  and rely on hcloud_network_route to send 0.0.0.0/0 here.
# =============================================================================

package_update: false
package_upgrade: false

write_files:
  - path: /etc/sysctl.d/99-iyziops-nat.conf
    permissions: '0644'
    content: |
      net.ipv4.ip_forward = 1
      net.ipv4.conf.all.forwarding = 1

  - path: /etc/systemd/system/iyziops-nat-masquerade.service
    permissions: '0644'
    content: |
      [Unit]
      Description=iyziops NAT box MASQUERADE rule
      After=network-online.target
      Wants=network-online.target
      [Service]
      Type=oneshot
      RemainAfterExit=true
      ExecStart=/bin/sh -c '/sbin/iptables -t nat -C POSTROUTING -s ${private_subnet_cidr} ! -d ${private_subnet_cidr} -j MASQUERADE 2>/dev/null || /sbin/iptables -t nat -A POSTROUTING -s ${private_subnet_cidr} ! -d ${private_subnet_cidr} -j MASQUERADE'
      [Install]
      WantedBy=multi-user.target

runcmd:
  - sysctl --system
  - systemctl daemon-reload
  - systemctl enable --now iyziops-nat-masquerade.service
