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

# PR-A security hardening — stored-credential encryption key.
# DEBUGDUCK_MASTER_KEY must be a stable Fernet key sourced from the
# operator's secret manager. FERNET_REQUIRE_ENV_KEY=on prevents the
# container from silently auto-generating a replacement key when the
# real one isn't mounted — doing so orphans every encrypted credential
# in the database on pod restart. See
# docs/plans/2026-04-18-fernet-key-env-migration.md for rotation.
{{- if .Values.encryption.masterKey.existingSecret }}
- name: DEBUGDUCK_MASTER_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.encryption.masterKey.existingSecret }}
      key:  {{ .Values.encryption.masterKey.secretKey | default "master-key" }}
- name: FERNET_REQUIRE_ENV_KEY
  value: "on"
{{- end }}

# PR-A session ownership — set to "on" in managed multi-tenant
# deployments to enforce session-level ownership on /chat and /cancel.
# Default "off" — zero behavior change for single-tenant dev/demo.
- name: SESSION_OWNERSHIP_CHECK
  value: {{ .Values.security.sessionOwnershipCheck | default "off" | quote }}
{{- end -}}
