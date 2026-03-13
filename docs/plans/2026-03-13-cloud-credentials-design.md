# Cloud Provider Credential Forms — Design

## Goal

Replace the generic auth dropdown for cloud providers (AWS, Azure, GCP, Oracle) with provider-specific credential forms in a dedicated "Cloud Providers" section on the Settings page.

## Architecture

A new `CloudProvidersSection.tsx` component renders below the existing `GlobalIntegrationsSection` inside `IntegrationHub.tsx`. Cloud service types (`aws`, `azure`, `gcp`, `oracle`) are filtered out of `GlobalIntegrationsSection` so they only appear in the new section. Each provider gets a collapsible card with tailored credential fields, region/subscription config, and a test-connection button. Credentials are packed into a JSON string for `auth_data` — the existing encryption pipeline handles it with zero backend schema changes.

## Tech Stack

- React + TypeScript + Tailwind (frontend)
- FastAPI + Pydantic (backend — minimal changes)
- Existing Fernet/K8s credential encryption (unchanged)

---

## Provider Credential Forms

### AWS

| Field | Input Type | Required | Stored In |
|-------|-----------|----------|-----------|
| Access Key ID | `text` | Yes | `auth_data` (JSON) |
| Secret Access Key | `password` | Yes | `auth_data` (JSON) |
| IAM Role ARN | `text` | No | `auth_data` (JSON) |
| External ID | `text` | No (shown when Role ARN filled) | `auth_data` (JSON) |
| Session Token | `password` | No | `auth_data` (JSON) |
| Regions | multi-select chips | Yes (default: `us-east-1`) | `config.regions` |

`auth_method` is set to `iam_role` automatically.

`auth_data` JSON shape:
```json
{
  "access_key_id": "AKIA...",
  "secret_access_key": "wJal...",
  "role_arn": "",
  "external_id": "",
  "session_token": ""
}
```

### Azure

| Field | Input Type | Required | Stored In |
|-------|-----------|----------|-----------|
| Tenant ID | `text` | Yes | `auth_data` (JSON) |
| Client ID | `text` | Yes | `auth_data` (JSON) |
| Client Secret | `password` | Yes | `auth_data` (JSON) |
| Subscriptions | tag input (comma-separated) | No | `config.subscriptions` |

`auth_method` is set to `azure_sp` automatically.

`auth_data` JSON shape:
```json
{
  "tenant_id": "xxxxxxxx-xxxx-...",
  "client_id": "xxxxxxxx-xxxx-...",
  "client_secret": "..."
}
```

### GCP

| Field | Input Type | Required | Stored In |
|-------|-----------|----------|-----------|
| Service Account JSON | `textarea` (paste) | Yes | `auth_data` (the JSON itself) |
| Project ID | read-only text (auto-extracted) | — | `config.project_id` |

`auth_method` is set to `gcp_sa` (new value) automatically.

`auth_data` is the raw service account JSON string. Frontend extracts `project_id` from the parsed JSON and writes it to `config.project_id` for display.

### Oracle

| Field | Input Type | Required | Stored In |
|-------|-----------|----------|-----------|
| Tenancy OCID | `text` | Yes | `auth_data` (JSON) |
| User OCID | `text` | Yes | `auth_data` (JSON) |
| Private Key (PEM) | `textarea` | Yes | `auth_data` (JSON) |
| Key Fingerprint | `text` | Yes | `auth_data` (JSON) |
| Regions | multi-select chips | Yes | `config.regions` |

`auth_method` is set to `oci_config` automatically.

`auth_data` JSON shape:
```json
{
  "tenancy_ocid": "ocid1.tenancy.oc1...",
  "user_ocid": "ocid1.user.oc1...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "fingerprint": "aa:bb:cc:..."
}
```

---

## UI Layout

### Card Grid

```
┌─ Cloud Providers ────────────────────────────────────────────┐
│                                                              │
│  ┌─ AWS ──────────────┐  ┌─ Azure ────────────────┐        │
│  │ ☁ Amazon Web Svcs  │  │ ☁ Microsoft Azure      │        │
│  │ ● Connected        │  │ ○ Not Linked           │        │
│  │ ▾ (click expand)   │  │ ▾ (click expand)       │        │
│  └────────────────────┘  └────────────────────────┘        │
│                                                              │
│  ┌─ GCP ──────────────┐  ┌─ Oracle ───────────────┐        │
│  │ ☁ Google Cloud     │  │ ☁ Oracle Cloud         │        │
│  │ ○ Not Linked       │  │ ○ Not Linked           │        │
│  │ ▾ (click expand)   │  │ ▾ (click expand)       │        │
│  └────────────────────┘  └────────────────────────┘        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Expanded Card (AWS example)

```
┌─ AWS ─────────────────────────────────────────────────┐
│ ☁ Amazon Web Services                    ● Connected  │
│───────────────────────────────────────────────────────│
│                                                       │
│  Access Key ID          Secret Access Key             │
│  ┌─────────────────┐   ┌─────────────────┐           │
│  │ AKIA••••••••    │   │ ••••••••••••••  │           │
│  └─────────────────┘   └─────────────────┘           │
│                                                       │
│  IAM Role ARN (optional)                              │
│  ┌────────────────────────────────────────┐           │
│  │ arn:aws:iam::123456:role/DebugDuck    │           │
│  └────────────────────────────────────────┘           │
│                                                       │
│  External ID (optional)    Session Token (optional)   │
│  ┌─────────────────┐   ┌─────────────────┐           │
│  │                 │   │ ••••••••••••••  │           │
│  └─────────────────┘   └─────────────────┘           │
│                                                       │
│  Regions                                              │
│  [us-east-1 ✕] [eu-west-1 ✕] [+ Add]               │
│                                                       │
│  [Test Connection]                        [Save]      │
└───────────────────────────────────────────────────────┘
```

### Styling

- Cards use the existing dark theme: `bg-[#0f2023]` background, `border-[#224349]`
- Provider accent colors on the card top border: AWS `#ff9900`, Azure `#0078d4`, GCP `#4285f4`, Oracle `#c4161c`
- Status badge: green dot for connected, muted for not linked, red for error
- Inputs: same style as existing form fields in GlobalIntegrationsSection
- Region chips: `bg-[#07b6d5]/10 text-[#07b6d5]` with ✕ dismiss button

---

## Data Flow

1. **Load**: `IntegrationHub` fetches all `globalIntegrations`, passes cloud-type ones to `CloudProvidersSection`
2. **Edit**: User expands a card, fills fields. Credential fields → JSON string → `auth_data`. Config fields → `config` object.
3. **Save**: Calls existing `updateGlobalIntegration(id, { auth_method, auth_data, config })`. Backend encrypts `auth_data` via `CredentialResolver.encrypt_and_store()`.
4. **Display**: On reload, `has_credentials: true` → show masked placeholders (••••). Config fields (regions, subscriptions) come back in `config` and render normally.
5. **Test**: Calls existing `testGlobalIntegration(id)`. Backend decrypts credentials, runs provider-specific health check.

---

## Backend Changes

### 1. profile_models.py

- Add `"gcp_sa"` to `auth_method` Literal
- Add GCP entry to `DEFAULT_GLOBAL_INTEGRATIONS`:
  ```python
  {
      "id": "cloud-gcp",
      "name": "Google Cloud Platform",
      "service_type": "gcp",
      "auth_method": "gcp_sa",
      "config": {"project_id": "", "regions": []},
  }
  ```

### 2. probe.py — Cloud Test Connections

Add provider-specific test logic to `GlobalProbe.test_connection()`:

- **AWS**: Parse JSON `auth_data`, call STS `GetCallerIdentity` via boto3
- **Azure**: Parse JSON `auth_data`, authenticate with `ClientSecretCredential`, call Azure Resource Manager `/subscriptions`
- **GCP**: Parse service account JSON, build credentials, call `projects.get`
- **Oracle**: Parse JSON `auth_data`, build OCI signer, call Identity `GetTenancy`

Falls back to `{"reachable": true, "message": "Credentials saved (SDK not installed)"}` if provider SDK is not available (boto3, azure-identity, etc.).

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/components/Settings/CloudProvidersSection.tsx` | Create | New component — 4 provider cards with credential forms |
| `frontend/src/components/Settings/IntegrationHub.tsx` | Modify | Import CloudProvidersSection, split integrations list, pass cloud ones down |
| `frontend/src/components/Settings/GlobalIntegrationsSection.tsx` | Modify | Filter out `aws`, `azure`, `gcp`, `oracle` from render |
| `backend/src/integrations/profile_models.py` | Modify | Add `gcp_sa` auth method, add GCP seed defaults |
| `backend/src/integrations/probe.py` | Modify | Add cloud-specific test connection handlers |

---

## Out of Scope

- Cloud resource discovery/sync (already exists in `cloud_store.py`)
- Credential rotation UI
- MFA / interactive login flows
- Certificate-based Azure auth
- Cloud provider adapter refactoring (adapters already work)
