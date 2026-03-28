{{/*
Common labels for haven-rabbitmq resources.
*/}}
{{- define "haven-rabbitmq.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: rabbitmq
haven.io/plan: {{ .Values.plan }}
{{- end -}}
