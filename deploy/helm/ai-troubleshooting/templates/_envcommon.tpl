{{/*
Shared env block for web + worker pods. Keeps the two Deployments in sync —
adding a new env var here propagates to both.

Composes DATABASE_URL + REDIS_URL at pod start from POSTGRES_PASSWORD +
REDIS_PASSWORD (referenced via valueFrom from the upstream Secrets) using
the standard `$(VAR)` env interpolation pattern. This avoids passing
plaintext passwords through the chart's own Secret.
*/}}
{{- define "aitsh.commonEnv" -}}
# ConfigMap mount — feature flags, hosts, ports, log level.
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "aitsh.postgresPasswordSecretName" . }}
      key:  {{ include "aitsh.postgresPasswordSecretKey" . }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "aitsh.redisPasswordSecretName" . }}
      key:  {{ include "aitsh.redisPasswordSecretKey" . }}

# Composed DSNs — k8s env interpolation of the password vars above.
- name: DATABASE_URL
  value: "postgresql+asyncpg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)"
- name: REDIS_URL
  value: "redis://:$(REDIS_PASSWORD)@$(REDIS_HOST):$(REDIS_PORT)/0"

# Anthropic — default key (required).
- name: ANTHROPIC_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.anthropic.defaultKey.existingSecret }}
      key:  {{ .Values.anthropic.defaultKey.secretKey }}

# Anthropic — named override keys (operator-defined).
{{- range .Values.anthropic.namedKeys }}
- name: {{ include "aitsh.anthropicEnvVar" .name }}
  valueFrom:
    secretKeyRef:
      name: {{ .existingSecret }}
      key:  {{ .secretKey }}
{{- end }}
{{- end -}}
