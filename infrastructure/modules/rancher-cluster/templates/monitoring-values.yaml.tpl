# rancher-monitoring Helm values (Haven Check #14: Metrics)
# Based on kube-prometheus-stack (Prometheus + Grafana)
# Note: global.cattle.clusterId/clusterName are auto-injected by Rancher
prometheus:
  prometheusSpec:
    evaluationInterval: "1m"
    scrapeInterval: "1m"
    retentionSize: "${retention_size}"
    retention: "${retention_days}"
    resources:
      requests:
        cpu: "${prometheus_cpu_request}"
        memory: "${prometheus_memory_request}"
      limits:
        memory: "${prometheus_memory_limit}"
    tolerations:
      - operator: "Exists"
grafana:
  defaultDashboardsEnabled: true
  sidecar:
    dashboards:
      searchNamespace: ALL
  tolerations:
    - operator: "Exists"
alertmanager:
  alertmanagerSpec:
    tolerations:
      - operator: "Exists"
prometheusOperator:
  tolerations:
    - operator: "Exists"
nodeExporter:
  tolerations:
    - operator: "Exists"
