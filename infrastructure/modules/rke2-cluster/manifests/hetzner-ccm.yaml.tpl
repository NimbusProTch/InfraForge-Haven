---
# =============================================================================
#  Hetzner Cloud Controller Manager — bootstrap manifest
# =============================================================================
#  Installs hcloud-cloud-controller-manager as a raw Deployment via RKE2's
#  /var/lib/rancher/rke2/server/manifests/ auto-deploy directory. RKE2 applies
#  YAML manifests in this directory directly with kubectl-style server-side
#  apply — no helm-install Job pod required.
#
#  Why NOT a HelmChart resource:
#    Wrapping the chart in a `helm.cattle.io/v1 HelmChart` resource means
#    RKE2's Helm Controller spawns a `helm-install-...` Job pod inside the
#    cluster to run `helm install`. That pod uses the standard "system addon"
#    pod template, which does NOT tolerate the
#    `node.cloudprovider.kubernetes.io/uninitialized:NoSchedule` taint that
#    kubelet sets on every node when --cloud-provider=external is passed.
#    Result: the helm-install pod cannot schedule anywhere because every
#    node is uninitialized, and CCM never starts to remove the taint —
#    bootstrap deadlock.
#
#    Using raw resources sidesteps the helm-install Job entirely. The
#    Deployment lands directly via RKE2's manifest applier (which runs
#    inside rke2-server, not as a Pod), and the CCM Pod itself tolerates
#    the uninitialized taint and runs hostNetwork so it can start before
#    Cilium is ready.
#
#  This pattern is documented in kube-hetzner and hcloud-k8s as the only
#  reliable way to install Hetzner CCM on a fresh cluster.
#
#  Source: https://github.com/hetznercloud/hcloud-cloud-controller-manager/
#          releases/download/v1.25.1/ccm-networks.yaml
#  We embed the manifest verbatim (with our own hcloud Secret override above
#  the upstream content) so the bootstrap is reproducible without internet.
# =============================================================================

apiVersion: v1
kind: Secret
metadata:
  name: hcloud
  namespace: kube-system
type: Opaque
stringData:
  token: "${hcloud_token}"
  network: "${network_name}"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: hcloud-cloud-controller-manager
  namespace: kube-system
---
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: "system:hcloud-cloud-controller-manager"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: hcloud-cloud-controller-manager
    namespace: kube-system
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hcloud-cloud-controller-manager
  namespace: kube-system
spec:
  replicas: 1
  revisionHistoryLimit: 2
  selector:
    matchLabels:
      app: hcloud-cloud-controller-manager
  template:
    metadata:
      labels:
        app: hcloud-cloud-controller-manager
    spec:
      serviceAccountName: hcloud-cloud-controller-manager
      dnsPolicy: Default
      tolerations:
        # Allow CCM itself to schedule on nodes that have not yet been
        # initialized by CCM (chicken-and-egg breaker).
        - key: "node.cloudprovider.kubernetes.io/uninitialized"
          value: "true"
          effect: "NoSchedule"
        - key: "CriticalAddonsOnly"
          operator: "Exists"
        # Allow CCM to schedule on control plane nodes (kube-hetzner runs
        # CCM only on masters; we follow the same convention).
        - key: "node-role.kubernetes.io/master"
          effect: NoSchedule
          operator: Exists
        - key: "node-role.kubernetes.io/control-plane"
          effect: NoSchedule
          operator: Exists
        - key: "node.kubernetes.io/not-ready"
          effect: "NoExecute"
      # hostNetwork is required so CCM can run before Cilium has installed
      # pod networking. CCM is the thing that initializes nodes, so it has
      # to bypass the not-yet-existing pod network.
      hostNetwork: true
      containers:
        - name: hcloud-cloud-controller-manager
          args:
            - "--allow-untagged-cloud"
            - "--cloud-provider=hcloud"
            - "--route-reconciliation-period=30s"
            - "--webhook-secure-port=0"
            # We let Cilium IPAM (mode: kubernetes) handle pod CIDR
            # allocation. CCM's --allocate-node-cidrs path is harmless
            # because Cilium ignores both CCM and kube-controller-manager
            # CIDR writes and uses its own IPAM, but we keep the flag
            # because the upstream chart sets it and removing it would
            # diverge from the maintained manifest.
            - "--allocate-node-cidrs=true"
            - "--cluster-cidr=10.244.0.0/16"
            - "--leader-elect=false"
          env:
            - name: HCLOUD_TOKEN
              valueFrom:
                secretKeyRef:
                  key: token
                  name: hcloud
            - name: HCLOUD_NETWORK
              valueFrom:
                secretKeyRef:
                  key: network
                  name: hcloud
            # Routing the LB → node path through the private network is
            # what makes Cilium Gateway → CCM → Hetzner LB end-to-end work
            # without going through public IPs. Set unconditionally — the
            # ingress LB and all node networks live inside the same private
            # subnet by design.
            - name: HCLOUD_LOAD_BALANCERS_USE_PRIVATE_IP
              value: "true"
            - name: HCLOUD_LOAD_BALANCERS_DISABLE_PRIVATE_INGRESS
              value: "true"
            - name: HCLOUD_LOAD_BALANCERS_LOCATION
              value: "${ingress_lb_location}"
          image: docker.io/hetznercloud/hcloud-cloud-controller-manager:v${ccm_version}
          ports:
            - name: metrics
              containerPort: 8233
          resources:
            requests:
              cpu: 100m
              memory: 50Mi
      priorityClassName: "system-cluster-critical"
