{{/*
Common labels for haven-redis resources.
*/}}
{{- define "haven-redis.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: redis
haven.io/plan: {{ .Values.plan }}
{{- end -}}
