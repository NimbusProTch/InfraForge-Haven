{{/*
Common labels for haven-mysql resources.
*/}}
{{- define "haven-mysql.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/managed-by: haven
haven.io/service-type: mysql
haven.io/plan: {{ .Values.plan }}
{{- end -}}

{{/*
HAProxy replica count: 1 for small, 2 otherwise.
*/}}
{{- define "haven-mysql.haproxy-size" -}}
{{- if eq .Values.plan "small" -}}1{{- else -}}2{{- end -}}
{{- end -}}
