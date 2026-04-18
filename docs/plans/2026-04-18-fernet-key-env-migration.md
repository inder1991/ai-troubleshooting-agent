# Fernet key → env-var migration (deferred)

**Status:** deferred. Plan only — no implementation yet.
**Priority:** high (security hardening)
**Estimated effort:** ~150 lines + tests, 1 focused day.
**Owner:** TBD.
**Trigger to pick up:** first customer in a regulated vertical, first compliance audit finding, or when the tracked key is cited as a blocker. Otherwise schedule alongside the next security-themed PR batch.

## Problem statement

`data/.fernet_dev_key` is a **tracked file** holding a symmetric encryption key (Fernet / AES-CBC+HMAC) used by `backend/src/integrations/secret_store.py` to encrypt credentials at rest in the database — Jira / Confluence / Remedy / GitHub / ELK / Prometheus credentials saved via the Settings UI.

Three concrete failure modes:

1. **Shared key across all installs.** Every git clone reads the same key. Two separate dev teams can decrypt each other's stored credentials.
2. **Historical exposure.** The key has been in git since it was first committed; anyone with a past clone retains it forever. Deletion today doesn't rewind history.
3. **Default-defeats-itself in production.** A customer who deploys without explicitly overriding the key stores their production-encrypted credentials with a key that's visible in this public repo.
4. **No rotation story.** A file-backed key can't be rotated without forcing every install into a re-encryption migration.

The tracked file is named `.fernet_dev_key` — the author likely intended "dev only" — but the loader reads it unconditionally, so it's also the production default.

## Proposed fix

Move to standard env-var secret handling. Three-layer plumbing per the deployment-track conventions:

### Layer 1 — App reads from env

**`backend/src/integrations/secret_store.py`**

```python
def _load_fernet_key() -> bytes:
    raw = os.environ.get("AI_TSHOOT_FERNET_KEY", "").strip()
    if raw:
        return raw.encode()
    # Dev-mode fallback: per-process random key + LOUD warning.
    # Encrypted values won't survive restart — that's the point, so
    # no one accidentally ships without setting the env var.
    logger.warning(
        "AI_TSHOOT_FERNET_KEY is unset — generating a per-process key. "
        "Encrypted DB values WILL NOT survive a restart. Set "
        "AI_TSHOOT_FERNET_KEY in your environment for real operation."
    )
    return Fernet.generate_key()
```

Three properties:
- **Env-first**: explicit env var wins
- **Dev-safe**: fallback works for unit tests + solo local dev without forcing setup friction
- **Loud**: the warning makes "accidentally shipped without setting" visible in logs

### Layer 2 — Local dev

**`.env.example`** gains:

```bash
# Fernet symmetric encryption key — encrypts credentials stored in the DB.
# REQUIRED for production. Dev-mode falls back to a per-process random key
# (with a warning) if unset; stored values won't survive restart.
#
# Generate:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AI_TSHOOT_FERNET_KEY=
```

**`deploy/docker/compose.dev.yml`** threads the env var through to backend-web + backend-worker (already does pattern-matching on .env; single line add to the `x-backend-env` anchor).

**`deploy/docker/scripts/preflight.sh`** adds a warn-not-fail check:

```bash
if [[ -z "${AI_TSHOOT_FERNET_KEY:-}" ]]; then
  yellow "⚠ AI_TSHOOT_FERNET_KEY unset — using dev-mode ephemeral key."
fi
```

Doesn't block `make up` (too aggressive for first-time onboarding) but surfaces the risk.

### Layer 3 — Production (Helm)

**`deploy/helm/ai-troubleshooting/values.yaml`** gains:

```yaml
fernetKey:
  # REQUIRED. Pre-create a Secret:
  #   kubectl create secret generic ai-tshoot-fernet \
  #     --from-literal=key=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  existingSecret: ""
  secretKey: key
```

**`templates/_validation.tpl`** fail-fast:

```yaml
{{- if not .Values.fernetKey.existingSecret -}}
  {{- fail "fernetKey.existingSecret is required. Pre-create a Secret with a Fernet key — see docs/deployment.md §secrets-rotation." -}}
{{- end -}}
```

**`templates/_envcommon.tpl`** adds the env var via `valueFrom.secretKeyRef` — mirrors the Anthropic default-key pattern from B.11 exactly.

### Layer 4 — Cleanup

- `git rm data/.fernet_dev_key`
- `.gitignore`: add `data/*.key` and `data/.fernet*` to prevent re-adds
- Documented rotation procedure in `docs/deployment.md` — how to rotate without dropping existing encrypted data

## Operational trade-offs

### What gets harder

- **First-time developer onboarding** gains one step: copy `.env.example → .env`, run the one-liner, paste output. ~30s added to setup.
- **Existing dev databases** will have encrypted rows that no longer decrypt after the default key goes away. Solution: the dev-mode warning path keeps the default behavior; devs can migrate at their leisure by generating a real key and re-saving any Integrations via the Settings UI.

### What gets better

- **Different installs have different keys.** Compromise of one doesn't leak others.
- **Rotation becomes possible.** A documented procedure (dump → re-encrypt → swap key) is straightforward once the key lives in a Secret.
- **Compliance audits pass** for "encryption at rest" questions. Auditor sees "key comes from cluster Secret, managed by operator."

## Migration for existing installs

For production installs already on the old key (there may be zero today; documented for safety):

1. Operator generates the new key, creates the Secret.
2. Write a one-shot migration: load all credential rows → decrypt with old key → re-encrypt with new key. Ship as an Alembic migration or as a standalone `python -m src.scripts.rotate_fernet_key` script.
3. Roll the web + worker deployments with the new key mounted.
4. Delete the old key's Secret after verifying writes.

For v1 of this migration we ship only the code + chart wiring + env pattern. The rotation script is a follow-up on demand — no known customer using it yet.

## Files touched (when implementation lands)

| File | Change | Lines |
|---|---|---|
| `backend/src/integrations/secret_store.py` | Env-var loader + dev fallback | ~30 |
| `.env.example` | New var + instructions | +10 |
| `.gitignore` | Ignore key files | +3 |
| `data/.fernet_dev_key` | `git rm` | -1 file |
| `deploy/docker/compose.dev.yml` | Thread env var | +2 |
| `deploy/docker/scripts/preflight.sh` | Warn on unset | +5 |
| `deploy/helm/ai-troubleshooting/values.yaml` | `fernetKey.existingSecret` | +15 |
| `deploy/helm/ai-troubleshooting/templates/_envcommon.tpl` | `valueFrom.secretKeyRef` wiring | +10 |
| `deploy/helm/ai-troubleshooting/templates/_validation.tpl` | Fail-fast guard | +6 |
| `docs/deployment.md` | Secrets rotation section | +30 |
| `docs/local-dev.md` | Onboarding step | +10 |
| `backend/tests/integrations/test_secret_store_env.py` | Env-var load + dev fallback | ~40 |
| **Total** | | **~150** |

## Sequence notes

Runs cleanly after any of the current open work; no dependencies on the TracingAgent track or deployment-automation track. Standalone PR, independent review.

## Acceptance criteria

- [ ] `AI_TSHOOT_FERNET_KEY` read from env when set
- [ ] Per-process fallback works with a loud warning when unset
- [ ] Unit test proves env-var beats fallback
- [ ] Unit test proves fallback warns
- [ ] Chart install aborts with a clear error when `fernetKey.existingSecret` is empty
- [ ] `docs/deployment.md` documents key generation + rotation procedure
- [ ] `data/.fernet_dev_key` removed from tree; `.gitignore` prevents re-adds
- [ ] Existing dev workflows still work without setting the env var (fallback path)
- [ ] No regression in `tests/integrations/` suite

## Out of scope for this plan

- Rotation script (`rotate_fernet_key.py`) — build when first customer asks
- Migration of in-prod-encrypted values — no known install needs this yet
- External secrets integration (ExternalSecrets / sealed-secrets / Vault) — already covered by the Helm chart's `existingSecret`-only pattern; operator chooses the backing store
