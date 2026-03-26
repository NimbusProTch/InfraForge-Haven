{{/*
Return the app fullname (uses appSlug).
*/}}
{{- define "haven-app.fullname" -}}
{{- .Values.appSlug | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Standard labels applied to all resources.
*/}}
{{- define "haven-app.labels" -}}
app: {{ include "haven-app.fullname" . }}
app.kubernetes.io/name: {{ include "haven-app.fullname" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
haven/managed: "true"
haven.io/tenant: {{ .Values.tenantSlug | quote }}
{{- end -}}

{{/*
Selector labels used for pod matching.
*/}}
{{- define "haven-app.selectorLabels" -}}
app: {{ include "haven-app.fullname" . }}
{{- end -}}

{{/*
Generate the hostname for the application.
If httproute.hostname is set, use it directly.
Otherwise, build from appSlug + tenantSlug + domain.
*/}}
{{- define "haven-app.hostname" -}}
{{- if .Values.httproute.hostname -}}
  {{- .Values.httproute.hostname -}}
{{- else -}}
  {{- printf "%s.%s.apps.%s" .Values.appSlug .Values.tenantSlug .Values.httproute.domain -}}
{{- end -}}
{{- end -}}

{{/*
Compute effective replicas. For prod preset, enforce minimum of 2.
When autoscaling is enabled, this value is only the initial replica count.
*/}}
{{- define "haven-app.effectiveReplicas" -}}
{{- if eq .Values.preset "prod" -}}
  {{- max .Values.replicas 2 -}}
{{- else -}}
  {{- .Values.replicas -}}
{{- end -}}
{{- end -}}

{{/*
Return the probe port. Falls back to .Values.port if not explicitly set.
*/}}
{{- define "haven-app.probePort" -}}
{{- $probe := . -}}
{{- if $probe.port -}}
  {{- $probe.port -}}
{{- else -}}
  {{- "APP_PORT" -}}
{{- end -}}
{{- end -}}
