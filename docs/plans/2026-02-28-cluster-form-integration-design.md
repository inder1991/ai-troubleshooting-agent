# Cluster Form Integration Design

**Date:** 2026-02-28
**Status:** Approved
**Approach:** A — Inline profile creation with ad-hoc fallback

## Problem

The cluster diagnostics form has four gaps:

1. **Backend ignores credentials** — `MockClusterClient` is hardcoded; `connection_config` resolved from the profile is never passed to the cluster client.
2. **No kubeconfig backend support** — `StartSessionRequest` has no `auth_token` or `auth_method` fields. The form collects them but the backend discards them.
3. **Profile selection doesn't reflect stored credentials** — When a profile is selected, the form hardcodes `auth_method: 'token'` and doesn't indicate that credentials are already stored.
4. **No inline cluster creation** — Users must navigate to the Integration Hub to add a cluster before they can run cluster diagnostics.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Credential persistence | Both — "Save this cluster" checkbox, default checked | One-time users skip saving; repeat users get reusable profiles |
| Kubeconfig input | Paste YAML + file upload | Paste for quick use, file upload for large kubeconfigs |
| Real K8s client | Out of scope | Form/profile wiring only; mock stays swappable via factory |
| Stored creds UX | Hide auth + green badge + "Override" link | Clean UX; profile creds are the default, manual override is opt-in |
| Architecture | Inline profile creation (Approach A) | Reuses existing profile/credential infrastructure entirely |

## Architecture

### Frontend: ClusterDiagnosticsFields Redesign

The form operates in two modes based on profile selection:

**Mode 1 — Profile Selected:**
- Profile dropdown shows stored clusters with status/environment badges (existing)
- Auth section is hidden
- Green badge: "Credentials stored" with a small "Override" link
- Override reveals the auth fields pre-set to the profile's auth method
- Remaining fields: namespace, resource type, symptoms

**Mode 2 — Manual Entry (no profile):**
- Cluster API URL field (required)
- Auth method toggle: Token | Kubeconfig
- Token: textarea for bearer token
- Kubeconfig: textarea for paste + file upload button (reads file via FileReader.readAsText, populates textarea)
- "Save this cluster" checkbox (default checked) with a "Cluster Name" text field when checked (auto-suggested from URL hostname)
- Remaining fields: namespace, resource type, symptoms

**On submit with "Save this cluster" checked:**
1. Call `createProfile()` via `profileApi.ts`
2. On success, set returned `profile_id` on form data
3. Then submit `startSessionV4()` with `profile_id`

**On submit without saving:**
1. Pass `cluster_url`, `auth_token`, `auth_method` directly in the session start request
2. Backend uses them as ad-hoc overrides

**When no profiles exist (first-time user):**
- Profile dropdown is hidden (existing `profiles.length > 0` guard)
- All fields shown in manual entry mode
- "Save this cluster" checked by default

### Backend: StartSessionRequest + Session Creation

Add optional fields to `StartSessionRequest` in `models.py`:
- `authToken: Optional[str]` — bearer token or kubeconfig contents
- `authMethod: Optional[str]` — `"token"` or `"kubeconfig"`

These are only used for ad-hoc mode. When `profile_id` is present, the backend resolves credentials from the profile store and ignores these fields.

Modify `start_session()` in `routes_v4.py` for the cluster path:
1. `resolve_active_profile(profile_id)` → `connection_config` (existing)
2. If no `connection_config` AND ad-hoc fields provided → build minimal `ResolvedConnectionConfig` from `request.clusterUrl` + `request.authToken`
3. Pass `connection_config` to cluster client factory
4. Store `connection_config` reference in session dict

Cluster client factory:
```python
def create_cluster_client(connection_config=None):
    # Future: return KubernetesClient(connection_config) when implemented
    return MockClusterClient(platform="openshift")
```

### Kubeconfig File Upload

Frontend-only feature:
- Button styled as "Upload .kubeconfig" alongside the textarea
- Accepts `.yaml`, `.yml`, and extensionless files
- Reads file via `FileReader.readAsText()`, populates the textarea
- User can edit after upload
- No file sent to backend — only text content goes as `auth_token`
- Backend stores kubeconfig contents in `auth_credential_handle` (encrypted via `CredentialResolver`)
- `auth_method` field distinguishes token from kubeconfig for future real K8s client

### Profile Selection UX

When a profile with stored credentials is selected:
1. Hide auth section (token/kubeconfig fields disappear)
2. Show credential badge below profile dropdown: `[green dot] prod  https://...  [shield] Credentials stored  [Override]`
3. "Override" link reveals auth section for one-time credential override (doesn't modify stored profile)
4. "Use stored" link reverts to stored credentials

## Validation + Error Handling

**Form validation:**
- Cluster URL: required, must match `https?://`
- Auth: required when no profile selected (or override active)
- Cluster name: required when "Save this cluster" checked; auto-suggested from URL hostname

**Save profile failure:**
- If `createProfile()` fails, show toast error and fall back to ad-hoc mode
- Message: "Couldn't save profile: [reason]. Proceeding with one-time credentials."

**Backend fallback chain:**
1. `profile_id` → `resolve_active_profile()` → full `connection_config`
2. No profile but `authToken` + `clusterUrl` → build minimal `connection_config`
3. Neither → 422: "Cluster URL and credentials are required"

## Out of Scope

- **Real KubernetesClient** — mock stays, factory is the extension point
- **Profile editing from form** — users go to Integration Hub for that
- **Kubeconfig context selection** — uses default context

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx` | Redesign: hide auth when profile has creds, credential badge, override link, file upload, save checkbox, cluster name field |
| `frontend/src/types/index.ts` | Add `auth_token`, `auth_method`, `save_cluster`, `cluster_name` to `ClusterDiagnosticsForm` |
| `backend/src/api/models.py` | Add `authToken`, `authMethod` optional fields to `StartSessionRequest` |
| `backend/src/api/routes_v4.py` | Wire `connection_config` into cluster session creation, add ad-hoc fallback, add `create_cluster_client()` factory |
| `backend/tests/test_cluster_routing.py` | Test ad-hoc credentials flow, test profile-based flow, test 422 when no credentials |

## Testing

1. Profile selected with stored creds → auth hidden, badge shown, session starts with profile credentials
2. Manual entry with "Save" checked → profile created, then session starts with new profile_id
3. Manual entry without save → ad-hoc credentials passed, session starts
4. Save fails → toast error, session starts with ad-hoc credentials
5. No profile, no credentials → submit disabled, 422 on backend
6. File upload → textarea populated with file contents
7. Override link → auth fields appear, stored creds not used
