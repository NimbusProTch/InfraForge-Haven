# rancher-logging Helm values (Haven Check #13: Log aggregation)
# Based on Banzai Cloud logging operator
tolerations:
  - operator: "Exists"
additionalLoggingSources:
  rke2:
    enabled: true
fluentbit:
  tolerations:
    - operator: "Exists"
  resources:
    requests:
      cpu: "${fluentbit_cpu_request}"
      memory: "${fluentbit_memory_request}"
    limits:
      memory: "${fluentbit_memory_limit}"
fluentd:
  tolerations:
    - operator: "Exists"
  resources:
    requests:
      cpu: "${fluentd_cpu_request}"
      memory: "${fluentd_memory_request}"
    limits:
      memory: "${fluentd_memory_limit}"
