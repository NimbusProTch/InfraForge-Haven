{{/*
haven-pg/_helpers.tpl
*/}}

{{/* Cluster name — falls back to .Release.Name */}}
{{- define "haven-pg.name" -}}
{{- .Values.name | default .Release.Name }}
{{- end }}

{{/* Namespace */}}
{{- define "haven-pg.namespace" -}}
{{- .Values.namespace | default .Release.Namespace }}
{{- end }}

{{/* Resolved instance count: 3 for prod, 1 for dev */}}
{{- define "haven-pg.instances" -}}
{{- if eq .Values.tier "prod" -}}3{{- else -}}{{ .Values.instances | default 1 }}{{- end }}
{{- end }}

{{/* Resolved storage size */}}
{{- define "haven-pg.storageSize" -}}
{{- if eq .Values.tier "prod" -}}20Gi{{- else -}}{{ .Values.storage.size | default "5Gi" }}{{- end }}
{{- end }}

{{/* True if backup should be enabled (explicitly or because tier=prod) */}}
{{- define "haven-pg.backupEnabled" -}}
{{- if or .Values.backup.enabled (eq .Values.tier "prod") -}}true{{- else -}}false{{- end }}
{{- end }}

{{/* S3 destination path */}}
{{- define "haven-pg.s3Destination" -}}
s3://{{ .Values.backup.bucketName }}/{{ .Values.tenantSlug }}/postgres/{{ include "haven-pg.name" . }}
{{- end }}

{{/* Common labels */}}
{{- define "haven-pg.labels" -}}
app.kubernetes.io/name: {{ include "haven-pg.name" . }}
app.kubernetes.io/managed-by: haven-platform
haven.nl/tenant: {{ .Values.tenantSlug }}
{{- end }}
