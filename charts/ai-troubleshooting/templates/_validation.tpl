{{/*
Fail-fast validations — invoked from each rendered template via
`{{- include "aitsh.validate" . -}}`. Catches operator misconfiguration at
`helm install` / `helm upgrade` time with a clear error rather than at
runtime in a crashloop.
*/}}

{{- define "aitsh.validate" -}}
  {{- include "aitsh.validate.databases" . -}}
  {{- include "aitsh.validate.cache" . -}}
  {{- include "aitsh.validate.anthropic" . -}}
  {{- include "aitsh.validate.networking" . -}}
{{- end -}}

{{/* ── Postgres mutual exclusion ───────────────────────────────────────── */}}
{{- define "aitsh.validate.databases" -}}
{{- if and .Values.postgresql.enabled .Values.externalDatabase.enabled -}}
  {{- fail "Cannot enable both postgresql.enabled AND externalDatabase.enabled. Pick one (bundled vs external)." -}}
{{- end -}}
{{- if and (not .Values.postgresql.enabled) (not .Values.externalDatabase.enabled) -}}
  {{- fail "One of postgresql.enabled or externalDatabase.enabled must be true." -}}
{{- end -}}
{{- if .Values.externalDatabase.enabled -}}
  {{- if not .Values.externalDatabase.existingSecret -}}
    {{- fail "externalDatabase.existingSecret is required when externalDatabase.enabled=true (existingSecret-only credential pattern; see D.28)." -}}
  {{- end -}}
  {{- if not .Values.externalDatabase.host -}}
    {{- fail "externalDatabase.host is required when externalDatabase.enabled=true." -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/* ── Redis mutual exclusion ──────────────────────────────────────────── */}}
{{- define "aitsh.validate.cache" -}}
{{- if and .Values.redis.enabled .Values.externalRedis.enabled -}}
  {{- fail "Cannot enable both redis.enabled AND externalRedis.enabled. Pick one (bundled vs external)." -}}
{{- end -}}
{{- if and (not .Values.redis.enabled) (not .Values.externalRedis.enabled) -}}
  {{- fail "One of redis.enabled or externalRedis.enabled must be true." -}}
{{- end -}}
{{- if .Values.externalRedis.enabled -}}
  {{- if not .Values.externalRedis.existingSecret -}}
    {{- fail "externalRedis.existingSecret is required when externalRedis.enabled=true." -}}
  {{- end -}}
  {{- if not .Values.externalRedis.host -}}
    {{- fail "externalRedis.host is required when externalRedis.enabled=true." -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/* ── Anthropic key store ─────────────────────────────────────────────── */}}
{{- define "aitsh.validate.anthropic" -}}
{{- if not .Values.anthropic.defaultKey.existingSecret -}}
  {{- fail "anthropic.defaultKey.existingSecret is required. Pre-create a Secret containing the default Anthropic API key and reference it here (existingSecret-only credential pattern)." -}}
{{- end -}}
{{- range .Values.anthropic.namedKeys -}}
  {{- if not .name -}}
    {{- fail "anthropic.namedKeys[*].name is required (operator-chosen logical name like 'premium' or 'cheap')." -}}
  {{- end -}}
  {{- if not (regexMatch "^[a-z][a-z0-9-]*$" .name) -}}
    {{- fail (printf "anthropic.namedKeys[].name %q is invalid. Use lowercase letters, digits, and hyphens; must start with a letter." .name) -}}
  {{- end -}}
  {{- if not .existingSecret -}}
    {{- fail (printf "anthropic.namedKeys[%s].existingSecret is required." .name) -}}
  {{- end -}}
{{- end -}}
{{/* Detect duplicate names. */}}
{{- $seen := dict -}}
{{- range .Values.anthropic.namedKeys -}}
  {{- if hasKey $seen .name -}}
    {{- fail (printf "anthropic.namedKeys: duplicate name %q." .name) -}}
  {{- end -}}
  {{- $_ := set $seen .name true -}}
{{- end -}}
{{- end -}}

{{/* ── Ingress vs Route mutual exclusion ───────────────────────────────── */}}
{{- define "aitsh.validate.networking" -}}
{{- if and .Values.ingress.enabled .Values.route.enabled -}}
  {{- fail "Cannot enable both ingress.enabled AND route.enabled. Use ingress on vanilla K8s, route on OpenShift." -}}
{{- end -}}
{{- if and .Values.openshift.enabled .Values.ingress.enabled -}}
  {{- fail "openshift.enabled=true is incompatible with ingress.enabled=true. Use route.enabled=true on OpenShift." -}}
{{- end -}}
{{- end -}}
