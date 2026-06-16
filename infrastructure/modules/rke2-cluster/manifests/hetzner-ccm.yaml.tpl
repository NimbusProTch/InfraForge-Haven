---
# Hetzner CCM — raw Deployment via RKE2 /var/lib/rancher/rke2/server/manifests/.
# NOT a helm.cattle.io HelmChart: the helm-install Job pod can't tolerate the
# uninitialized taint → bootstrap deadlock (see CLAUDE.md CCM gotcha). Comments
# kept terse on purpose — this manifest is base64-embedded in the first-master
# cloud-init, which has a hard 32KB limit. Full rationale lives in CLAUDE.md.
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
        # CCM must schedule on not-yet-initialized nodes (chicken-and-egg) and
        # on control-plane nodes (kube-hetzner convention: CCM on masters).
        - key: "node.cloudprovider.kubernetes.io/uninitialized"
          value: "true"
          effect: "NoSchedule"
        - key: "CriticalAddonsOnly"
          operator: "Exists"
        - key: "node-role.kubernetes.io/master"
          effect: NoSchedule
          operator: Exists
        - key: "node-role.kubernetes.io/control-plane"
          effect: NoSchedule
          operator: Exists
        - key: "node.kubernetes.io/not-ready"
          effect: "NoExecute"
      # hostNetwork: CCM runs before Cilium installs pod networking.
      hostNetwork: true
      containers:
        - name: hcloud-cloud-controller-manager
          args:
            - "--allow-untagged-cloud"
            - "--cloud-provider=hcloud"
            # --controllers=*,-route disables the route-controller: it writes
            # orphan 10.42.x/24 routes that hang `tofu destroy` on subnet
            # deletion. nodeipam (--allocate-node-cidrs) is separate, stays on,
            # harmless. (Phase C14 — see CLAUDE.md.)
            - "--controllers=*,-route"
            - "--route-reconciliation-period=30s"
            - "--webhook-secure-port=0"
            # Cilium IPAM owns pod CIDRs; this flag is harmless, kept to match
            # the upstream chart.
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
            # LB → node path via the private network (Cilium Gateway → CCM →
            # Hetzner LB without public IPs).
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
