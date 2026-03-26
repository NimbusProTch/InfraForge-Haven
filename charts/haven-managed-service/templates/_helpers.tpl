{{/*
Determine instance count based on tier
*/}}
{{- define "managed-service.instances" -}}
{{- if eq .Values.tier "prod" -}}3{{- else -}}1{{- end -}}
{{- end -}}

{{/*
Determine storage size based on tier and service type
*/}}
{{- define "managed-service.storage" -}}
{{- if eq .Values.tier "prod" -}}
{{- if or (eq .Values.serviceType "postgres") (eq .Values.serviceType "mysql") (eq .Values.serviceType "mongodb") -}}20Gi{{- else if eq .Values.serviceType "redis" -}}5Gi{{- else -}}10Gi{{- end -}}
{{- else -}}
{{- if or (eq .Values.serviceType "postgres") (eq .Values.serviceType "mysql") (eq .Values.serviceType "mongodb") -}}5Gi{{- else if eq .Values.serviceType "redis" -}}1Gi{{- else -}}5Gi{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "managed-service.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: {{ .Values.serviceType }}
haven.io/tier: {{ .Values.tier }}
{{- end -}}
