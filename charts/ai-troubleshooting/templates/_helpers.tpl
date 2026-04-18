{{/*
Helper templates — names, labels, image references, DSN composition.
*/}}

{{/*
Resource name prefix. Defaults to <release>-<chart>; overridable via
.Values.global.fullnameOverride for custom branding.
*/}}
{{- define "aitsh.fullname" -}}
{{- if .Values.global.fullnameOverride -}}
{{- .Values.global.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.global.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "aitsh.name" -}}
{{- default .Chart.Name .Values.global.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aitsh.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Standard labels — applied to every resource.
*/}}
{{- define "aitsh.labels" -}}
helm.sh/chart: {{ include "aitsh.chart" . }}
{{ include "aitsh.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ai-troubleshooting
{{- end -}}

{{/*
Selector labels — used by Service + Deployment matchLabels.
Component label distinguishes web from worker.
*/}}
{{- define "aitsh.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aitsh.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "aitsh.web.selectorLabels" -}}
{{ include "aitsh.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end -}}

{{- define "aitsh.worker.selectorLabels" -}}
{{ include "aitsh.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end -}}

{{/*
Image reference. Falls back to .Chart.AppVersion if image.tag is empty.
*/}}
{{- define "aitsh.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{/*
ServiceAccount name.
*/}}
{{- define "aitsh.serviceAccountName" -}}
{{ include "aitsh.fullname" . }}
{{- end -}}

{{/*
Postgres host — bundled subchart svc OR external host.
*/}}
{{- define "aitsh.postgresHost" -}}
{{- if .Values.postgresql.enabled -}}
{{- default (printf "%s-postgresql" .Release.Name) .Values.postgresql.fullnameOverride -}}
{{- else -}}
{{- required "externalDatabase.host is required when postgresql.enabled=false" .Values.externalDatabase.host -}}
{{- end -}}
{{- end -}}

{{- define "aitsh.postgresPort" -}}
{{- if .Values.postgresql.enabled -}}5432{{- else -}}{{ .Values.externalDatabase.port | default 5432 }}{{- end -}}
{{- end -}}

{{- define "aitsh.postgresUser" -}}
{{- if .Values.postgresql.enabled -}}{{ .Values.postgresql.auth.username }}{{- else -}}{{ .Values.externalDatabase.username }}{{- end -}}
{{- end -}}

{{- define "aitsh.postgresDb" -}}
{{- if .Values.postgresql.enabled -}}{{ .Values.postgresql.auth.database }}{{- else -}}{{ .Values.externalDatabase.database }}{{- end -}}
{{- end -}}

{{/*
Postgres password — references the Bitnami subchart's auto-generated Secret
or the operator-provided externalDatabase.existingSecret. Returned as a
{name, key} pair via valueFrom.secretKeyRef.
*/}}
{{- define "aitsh.postgresPasswordSecretName" -}}
{{- if .Values.postgresql.enabled -}}
{{- default (printf "%s-postgresql" .Release.Name) .Values.postgresql.auth.existingSecret -}}
{{- else -}}
{{- required "externalDatabase.existingSecret is required when postgresql.enabled=false" .Values.externalDatabase.existingSecret -}}
{{- end -}}
{{- end -}}

{{- define "aitsh.postgresPasswordSecretKey" -}}
{{- if .Values.postgresql.enabled -}}password{{- else -}}{{ .Values.externalDatabase.existingSecretPasswordKey | default "password" }}{{- end -}}
{{- end -}}

{{/*
Redis host + auth — same dual-mode pattern.
*/}}
{{- define "aitsh.redisHost" -}}
{{- if .Values.redis.enabled -}}
{{- default (printf "%s-redis-master" .Release.Name) .Values.redis.fullnameOverride -}}
{{- else -}}
{{- required "externalRedis.host is required when redis.enabled=false" .Values.externalRedis.host -}}
{{- end -}}
{{- end -}}

{{- define "aitsh.redisPort" -}}
{{- if .Values.redis.enabled -}}6379{{- else -}}{{ .Values.externalRedis.port | default 6379 }}{{- end -}}
{{- end -}}

{{- define "aitsh.redisPasswordSecretName" -}}
{{- if .Values.redis.enabled -}}
{{- default (printf "%s-redis" .Release.Name) .Values.redis.auth.existingSecret -}}
{{- else -}}
{{- required "externalRedis.existingSecret is required when redis.enabled=false" .Values.externalRedis.existingSecret -}}
{{- end -}}
{{- end -}}

{{- define "aitsh.redisPasswordSecretKey" -}}
{{- if .Values.redis.enabled -}}redis-password{{- else -}}{{ .Values.externalRedis.existingSecretPasswordKey | default "password" }}{{- end -}}
{{- end -}}

{{/*
Anthropic key env-var name from a logical name:
  premium       -> ANTHROPIC_API_KEY_PREMIUM
  billing-team-a -> ANTHROPIC_API_KEY_BILLING_TEAM_A
Mirrors backend/src/llm/key_resolver.py:_normalize() exactly.
*/}}
{{- define "aitsh.anthropicEnvVar" -}}
{{- printf "ANTHROPIC_API_KEY_%s" (upper (replace "-" "_" .)) -}}
{{- end -}}
