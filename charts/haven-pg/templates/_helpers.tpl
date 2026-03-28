{{/*
Common labels for haven-pg resources.
*/}}
{{- define "haven-pg.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: postgres
haven.io/plan: {{ .Values.plan }}
{{- end -}}
