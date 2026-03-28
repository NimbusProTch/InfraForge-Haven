{{/*
Common labels for haven-mongodb resources.
*/}}
{{- define "haven-mongodb.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: mongodb
haven.io/plan: {{ .Values.plan }}
{{- end -}}
