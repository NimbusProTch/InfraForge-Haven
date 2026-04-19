# metrics-server on the iyziops cluster

The cluster already ships **`rke2-metrics-server`** as part of the upstream
RKE2 distribution. There is no separate ArgoCD `Application` for it because
RKE2's bundled metrics-server is installed by the embedded helm-controller
during cluster bootstrap and lives in `kube-system`.

Verify:

```bash
kubectl get apiservice v1beta1.metrics.k8s.io
# NAME                     SERVICE                           AVAILABLE   AGE
# v1beta1.metrics.k8s.io   kube-system/rke2-metrics-server   True        4d8h

kubectl top nodes
# NAME               CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
# iyziops-master-0   1207m        30%    5687Mi          73%
# ...
```

## How the API surfaces it

`api/app/routers/observability.py::get_pods` calls
`metrics.k8s.io/v1beta1/namespaces/{ns}/pods` via the Kubernetes
dynamic client and merges per-pod CPU + memory into the `/observability/pods`
response. The values are best-effort — when metrics-server is briefly
unavailable the endpoint still returns pod status without numbers.

## How the UI surfaces it

Two places:

1. **Observability tab** (existing) — per-pod CPU + memory bars, averaged
   "Avg CPU" / "Avg Memory" overview cards, auto-refresh every 5 s.
2. **App detail header** (new in PR #158) — compact `LiveResourceBadge`
   with averaged CPU% + Memory% pills. Visible from every tab so the
   operator does not have to navigate to Observability to see resource
   health. Polls the same endpoint every 10 s.

If a pod has no resource limits configured (`app.resource_cpu_limit` /
`memory_limit` empty on the `applications` table), the percentage is
reported as `null` and rendered as `—` in the UI rather than `0%`.

## When `LiveResourceBadge` shows `—`

- The pod is not yet ready (metrics-server takes ~30 s after pod start).
- The app has no resource limits set (percentages are computed against
  limits, not requests).
- metrics-server itself is degraded — check
  `kubectl -n kube-system get pods -l k8s-app=metrics-server`.
