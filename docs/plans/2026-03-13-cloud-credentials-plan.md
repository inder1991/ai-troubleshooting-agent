# Cloud Provider Credential Forms — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add provider-specific credential forms (access key, secret key, service principal, etc.) for AWS, Azure, GCP, and Oracle in a dedicated Cloud Providers section on the Settings page.

**Architecture:** A new `CloudProvidersSection.tsx` renders 4 collapsible provider cards with tailored credential fields. Cloud service types are filtered out of the existing `GlobalIntegrationsSection`. Credentials are packed as JSON into the existing `auth_data` field — zero database schema changes. Backend gets `gcp_sa` auth method and cloud-specific test connection handlers.

**Tech Stack:** React + TypeScript + Tailwind (frontend), FastAPI + Pydantic (backend), existing Fernet credential encryption

---

### Task 1: Add `gcp_sa` Auth Method and GCP Seed Defaults

**Files:**
- Modify: `backend/src/integrations/profile_models.py:98-102` (auth_method Literal)
- Modify: `backend/src/integrations/profile_models.py:118-198` (DEFAULT_GLOBAL_INTEGRATIONS)

**Step 1: Add `gcp_sa` to auth_method Literal**

In `backend/src/integrations/profile_models.py`, find line 98-102:
```python
auth_method: Literal[
    "basic_auth", "bearer_token", "api_key", "cloud_id",
    "api_token", "oauth2", "certificate", "none",
    "iam_role", "azure_sp", "oci_config",
] = "none"
```

Change to:
```python
auth_method: Literal[
    "basic_auth", "bearer_token", "api_key", "cloud_id",
    "api_token", "oauth2", "certificate", "none",
    "iam_role", "azure_sp", "oci_config", "gcp_sa",
] = "none"
```

**Step 2: Add GCP entry to DEFAULT_GLOBAL_INTEGRATIONS**

After the Oracle entry (line ~197, the last `},` in the list), add before the closing `]`:
```python
{
    "id": "cloud-gcp",
    "name": "Google Cloud Platform",
    "service_type": "gcp",
    "enabled": False,
    "base_url": "",
    "auth_method": "gcp_sa",
    "auth_credential_handle": None,
    "config": {
        "project_id": "",
        "regions": [],
    },
},
```

**Step 3: Verify**

Run: `cd backend && python -c "from src.integrations.profile_models import GlobalIntegration, DEFAULT_GLOBAL_INTEGRATIONS; gi = GlobalIntegration(**DEFAULT_GLOBAL_INTEGRATIONS[-1]); print(gi.service_type, gi.auth_method)"`
Expected: `gcp gcp_sa`

**Step 4: Commit**

```bash
git add backend/src/integrations/profile_models.py
git commit -m "feat(backend): add gcp_sa auth method and GCP seed defaults"
```

---

### Task 2: Add Cloud Test Connection Handlers to GlobalProbe

**Files:**
- Modify: `backend/src/integrations/probe.py:306-365` (test_connection, _build_auth_headers, _get_test_path)

**Context:** The current `test_connection` method does a simple HTTP GET with auth headers. Cloud providers don't work that way — AWS needs STS `GetCallerIdentity`, Azure needs a management API call, etc. We'll add a `_test_cloud_provider` method that parses the JSON `auth_data` and calls the appropriate SDK. Falls back gracefully if SDKs aren't installed.

**Step 1: Add cloud test method to GlobalProbe**

In `backend/src/integrations/probe.py`, add this method after `_get_test_path` (after line ~348):

```python
async def _test_cloud_provider(
    self, service_type: str, credentials: str | None
) -> EndpointProbeResult:
    """Test cloud provider connectivity using provider SDKs."""
    import json
    import time

    ep = EndpointProbeResult(name=service_type)
    if not credentials:
        ep.error = "No credentials configured"
        return ep

    try:
        cred_data = json.loads(credentials)
    except (json.JSONDecodeError, TypeError):
        ep.error = "Invalid credential format (expected JSON)"
        return ep

    start = time.monotonic()

    if service_type == "aws":
        try:
            import boto3
            kwargs: dict = {}
            if cred_data.get("access_key_id"):
                kwargs["aws_access_key_id"] = cred_data["access_key_id"]
                kwargs["aws_secret_access_key"] = cred_data.get("secret_access_key", "")
            if cred_data.get("session_token"):
                kwargs["aws_session_token"] = cred_data["session_token"]
            client = boto3.client("sts", **kwargs)
            identity = client.get_caller_identity()
            ep.reachable = True
            ep.latency_ms = round((time.monotonic() - start) * 1000, 1)
            ep.discovered_url = f"arn: {identity.get('Arn', 'unknown')}"
        except ImportError:
            ep.reachable = True
            ep.latency_ms = 0
            ep.discovered_url = "Credentials saved (boto3 not installed — cannot verify)"
        except Exception as e:
            ep.error = f"AWS auth failed: {e}"

    elif service_type == "azure":
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.resource import SubscriptionClient
            cred = ClientSecretCredential(
                tenant_id=cred_data.get("tenant_id", ""),
                client_id=cred_data.get("client_id", ""),
                client_secret=cred_data.get("client_secret", ""),
            )
            sub_client = SubscriptionClient(cred)
            subs = list(sub_client.subscriptions.list())
            ep.reachable = True
            ep.latency_ms = round((time.monotonic() - start) * 1000, 1)
            ep.discovered_url = f"{len(subs)} subscription(s) accessible"
        except ImportError:
            ep.reachable = True
            ep.latency_ms = 0
            ep.discovered_url = "Credentials saved (azure-identity not installed — cannot verify)"
        except Exception as e:
            ep.error = f"Azure auth failed: {e}"

    elif service_type == "gcp":
        try:
            from google.oauth2 import service_account
            from google.cloud import resourcemanager_v3
            info = json.loads(credentials) if isinstance(credentials, str) else cred_data
            sa_cred = service_account.Credentials.from_service_account_info(info)
            rm_client = resourcemanager_v3.ProjectsClient(credentials=sa_cred)
            project_id = info.get("project_id", "")
            if project_id:
                rm_client.get_project(name=f"projects/{project_id}")
            ep.reachable = True
            ep.latency_ms = round((time.monotonic() - start) * 1000, 1)
            ep.discovered_url = f"project: {project_id}"
        except ImportError:
            ep.reachable = True
            ep.latency_ms = 0
            ep.discovered_url = "Credentials saved (google-cloud SDK not installed — cannot verify)"
        except Exception as e:
            ep.error = f"GCP auth failed: {e}"

    elif service_type == "oracle":
        try:
            import oci
            config = {
                "tenancy": cred_data.get("tenancy_ocid", ""),
                "user": cred_data.get("user_ocid", ""),
                "fingerprint": cred_data.get("fingerprint", ""),
                "key_content": cred_data.get("private_key", ""),
                "region": "us-ashburn-1",
            }
            identity_client = oci.identity.IdentityClient(config)
            identity_client.get_tenancy(config["tenancy"])
            ep.reachable = True
            ep.latency_ms = round((time.monotonic() - start) * 1000, 1)
            ep.discovered_url = f"tenancy: {config['tenancy'][:30]}..."
        except ImportError:
            ep.reachable = True
            ep.latency_ms = 0
            ep.discovered_url = "Credentials saved (oci SDK not installed — cannot verify)"
        except Exception as e:
            ep.error = f"Oracle auth failed: {e}"

    else:
        ep.error = f"Unknown cloud provider: {service_type}"

    return ep
```

**Step 2: Route cloud providers in test_connection**

In the `test_connection` method (line ~306), add a cloud-provider check at the top, after the `if not url` guard (after line ~313):

```python
# Cloud providers use SDK-based tests, not HTTP
cloud_providers = {"aws", "azure", "gcp", "oracle"}
if service_type in cloud_providers:
    return await self._test_cloud_provider(service_type, credentials)
```

**Step 3: Verify**

Run: `cd backend && python -c "from src.integrations.probe import GlobalProbe; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/integrations/probe.py
git commit -m "feat(backend): add cloud provider test connection handlers"
```

---

### Task 3: Filter Cloud Providers out of GlobalIntegrationsSection

**Files:**
- Modify: `frontend/src/components/Settings/GlobalIntegrationsSection.tsx:156` (component body)

**Context:** Cloud providers (aws, azure, gcp, oracle) will now be rendered by `CloudProvidersSection`. We need to filter them out of `GlobalIntegrationsSection` so they don't appear in both places.

**Step 1: Add filter at top of component**

In `frontend/src/components/Settings/GlobalIntegrationsSection.tsx`, find the component function (line 156):
```typescript
const GlobalIntegrationsSection: React.FC<GlobalIntegrationsSectionProps> = ({
```

Inside the component body, before the first `return` or any JSX, add:
```typescript
const CLOUD_PROVIDERS = new Set(['aws', 'azure', 'gcp', 'oracle']);
const filteredIntegrations = integrations.filter(gi => !CLOUD_PROVIDERS.has(gi.service_type));
```

Then replace all references to `integrations` in the JSX with `filteredIntegrations`. This affects:
- The mapping that renders existing integration cards (search for `integrations.map` or `integrations.filter`)

Also remove the cloud options from the "Add Integration" dropdown (lines 286-289):
```jsx
<option value="aws">Amazon Web Services</option>
<option value="azure">Microsoft Azure</option>
<option value="oracle">Oracle Cloud</option>
<option value="gcp">Google Cloud Platform</option>
```

Delete those 4 lines.

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/Settings/GlobalIntegrationsSection.tsx
git commit -m "refactor(frontend): filter cloud providers out of GlobalIntegrationsSection"
```

---

### Task 4: Create CloudProvidersSection Component

**Files:**
- Create: `frontend/src/components/Settings/CloudProvidersSection.tsx`

**Context:** This is the main new component. It renders a 2x2 grid of collapsible provider cards. Each card expands to show provider-specific credential fields. All credential fields are packed into a JSON string for `auth_data`. Non-secret config (regions, subscriptions) goes into `config`.

**Step 1: Create the component file**

Create `frontend/src/components/Settings/CloudProvidersSection.tsx` with the full implementation:

```typescript
import React, { useState, useCallback } from 'react';
import type { GlobalIntegration } from '../../types/profiles';

// ── Provider definitions ──

const CLOUD_PROVIDERS = ['aws', 'azure', 'gcp', 'oracle'] as const;
type CloudProvider = (typeof CLOUD_PROVIDERS)[number];

interface ProviderMeta {
  displayName: string;
  accent: string;
  accentBg: string;
  authMethod: string;
  icon: string;
}

const PROVIDER_META: Record<CloudProvider, ProviderMeta> = {
  aws: {
    displayName: 'Amazon Web Services',
    accent: '#ff9900',
    accentBg: 'bg-[#ff9900]/10',
    authMethod: 'iam_role',
    icon: 'aws',
  },
  azure: {
    displayName: 'Microsoft Azure',
    accent: '#0078d4',
    accentBg: 'bg-[#0078d4]/10',
    authMethod: 'azure_sp',
    icon: 'cloud',
  },
  gcp: {
    displayName: 'Google Cloud Platform',
    accent: '#4285f4',
    accentBg: 'bg-[#4285f4]/10',
    authMethod: 'gcp_sa',
    icon: 'cloud',
  },
  oracle: {
    displayName: 'Oracle Cloud Infrastructure',
    accent: '#c4161c',
    accentBg: 'bg-[#c4161c]/10',
    authMethod: 'oci_config',
    icon: 'cloud',
  },
};

// ── Common AWS Regions ──

const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-central-1',
  'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
];

const ORACLE_REGIONS = [
  'us-ashburn-1', 'us-phoenix-1', 'eu-frankfurt-1',
  'eu-amsterdam-1', 'uk-london-1', 'ap-tokyo-1',
  'ap-mumbai-1', 'ap-sydney-1',
];

// ── Shared input style ──

const inputClass =
  'bg-[#0a1a1d] border border-[#224349] rounded-lg text-white text-sm placeholder-[#4a6670] focus:outline-none focus:border-[#07b6d5] transition-colors';

const labelClass = 'block text-xs font-medium text-[#8fc3cc] mb-1';

// ── Status helpers ──

function statusBadge(status: string) {
  if (status === 'connected') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-green-400">
        <span className="w-2 h-2 rounded-full bg-green-400" />
        Connected
      </span>
    );
  }
  if (status === 'conn_error') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-red-400">
        <span className="w-2 h-2 rounded-full bg-red-400" />
        Error
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-[#4a6670]">
      <span className="w-2 h-2 rounded-full bg-[#4a6670]" />
      Not Configured
    </span>
  );
}

// ── Region Chips Component ──

function RegionChips({
  regions,
  available,
  onChange,
}: {
  regions: string[];
  available: string[];
  onChange: (regions: string[]) => void;
}) {
  const [showDropdown, setShowDropdown] = useState(false);
  const remaining = available.filter((r) => !regions.includes(r));

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {regions.map((r) => (
        <span
          key={r}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#07b6d5]/10 text-[#07b6d5] text-xs"
        >
          {r}
          <button
            onClick={() => onChange(regions.filter((x) => x !== r))}
            className="hover:text-white ml-0.5"
          >
            ×
          </button>
        </span>
      ))}
      <div className="relative">
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-dashed border-[#224349] text-[#4a6670] text-xs hover:border-[#07b6d5] hover:text-[#07b6d5] transition-colors"
        >
          <span className="material-symbols-outlined text-xs">add</span>
          Add
        </button>
        {showDropdown && remaining.length > 0 && (
          <div className="absolute top-7 left-0 z-50 bg-[#0a1a1d] border border-[#224349] rounded-lg shadow-xl max-h-40 overflow-y-auto min-w-[140px]">
            {remaining.map((r) => (
              <button
                key={r}
                onClick={() => {
                  onChange([...regions, r]);
                  setShowDropdown(false);
                }}
                className="block w-full text-left px-3 py-1.5 text-xs text-[#8fc3cc] hover:bg-[#07b6d5]/10 hover:text-white"
              >
                {r}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Per-Provider Credential Forms ──

function AWSFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Access Key ID *</label>
          <input
            type="text"
            value={creds.access_key_id || ''}
            onChange={(e) => onCredsChange({ ...creds, access_key_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'AKIA...'}
          />
        </div>
        <div>
          <label className={labelClass}>Secret Access Key *</label>
          <input
            type="password"
            value={creds.secret_access_key || ''}
            onChange={(e) => onCredsChange({ ...creds, secret_access_key: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'wJal...'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>IAM Role ARN (optional — for cross-account access)</label>
        <input
          type="text"
          value={creds.role_arn || ''}
          onChange={(e) => onCredsChange({ ...creds, role_arn: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder="arn:aws:iam::123456789:role/DebugDuck"
        />
      </div>
      {creds.role_arn && (
        <div>
          <label className={labelClass}>External ID (optional)</label>
          <input
            type="text"
            value={creds.external_id || ''}
            onChange={(e) => onCredsChange({ ...creds, external_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder="External ID for assume-role"
          />
        </div>
      )}
      <div>
        <label className={labelClass}>Session Token (optional — for temporary credentials)</label>
        <input
          type="password"
          value={creds.session_token || ''}
          onChange={(e) => onCredsChange({ ...creds, session_token: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder={hasExisting ? '••••••••••••' : 'FwoGZX...'}
        />
      </div>
      <div>
        <label className={labelClass}>Regions</label>
        <RegionChips
          regions={(config.regions as string[]) || []}
          available={AWS_REGIONS}
          onChange={(regions) => onConfigChange({ ...config, regions })}
        />
      </div>
    </div>
  );
}

function AzureFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  const [subInput, setSubInput] = useState('');
  const subscriptions = (config.subscriptions as string[]) || [];

  return (
    <div className="space-y-3">
      <div>
        <label className={labelClass}>Tenant ID *</label>
        <input
          type="text"
          value={creds.tenant_id || ''}
          onChange={(e) => onCredsChange({ ...creds, tenant_id: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder={hasExisting ? '••••••••••••' : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Client ID *</label>
          <input
            type="text"
            value={creds.client_id || ''}
            onChange={(e) => onCredsChange({ ...creds, client_id: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'xxxxxxxx-xxxx-...'}
          />
        </div>
        <div>
          <label className={labelClass}>Client Secret *</label>
          <input
            type="password"
            value={creds.client_secret || ''}
            onChange={(e) => onCredsChange({ ...creds, client_secret: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'Client secret value'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>Subscriptions (optional)</label>
        <div className="flex flex-wrap items-center gap-1.5">
          {subscriptions.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#07b6d5]/10 text-[#07b6d5] text-xs"
            >
              {s}
              <button
                onClick={() =>
                  onConfigChange({ ...config, subscriptions: subscriptions.filter((x) => x !== s) })
                }
                className="hover:text-white ml-0.5"
              >
                ×
              </button>
            </span>
          ))}
          <input
            type="text"
            value={subInput}
            onChange={(e) => setSubInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && subInput.trim()) {
                onConfigChange({
                  ...config,
                  subscriptions: [...subscriptions, subInput.trim()],
                });
                setSubInput('');
              }
            }}
            className={`${inputClass} px-2 py-0.5 text-xs w-32`}
            placeholder="Add subscription ID..."
          />
        </div>
      </div>
    </div>
  );
}

function GCPFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  const handleJsonChange = (value: string) => {
    onCredsChange({ _raw_json: value });
    // Try to extract project_id
    try {
      const parsed = JSON.parse(value);
      if (parsed.project_id) {
        onConfigChange({ ...config, project_id: parsed.project_id });
      }
    } catch {
      // Not valid JSON yet — that's fine while typing
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <label className={labelClass}>Service Account JSON Key *</label>
        <textarea
          value={creds._raw_json || ''}
          onChange={(e) => handleJsonChange(e.target.value)}
          className={`${inputClass} w-full px-3 py-2 h-32 font-mono text-xs`}
          placeholder={
            hasExisting
              ? 'Credentials saved. Paste new JSON to replace.'
              : '{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}'
          }
        />
      </div>
      {config.project_id && (
        <div>
          <label className={labelClass}>Project ID (auto-detected)</label>
          <input
            type="text"
            value={(config.project_id as string) || ''}
            readOnly
            className={`${inputClass} w-full px-3 py-2 opacity-60 cursor-not-allowed`}
          />
        </div>
      )}
    </div>
  );
}

function OracleFields({
  creds,
  config,
  hasExisting,
  onCredsChange,
  onConfigChange,
}: {
  creds: Record<string, string>;
  config: Record<string, unknown>;
  hasExisting: boolean;
  onCredsChange: (c: Record<string, string>) => void;
  onConfigChange: (c: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Tenancy OCID *</label>
          <input
            type="text"
            value={creds.tenancy_ocid || ''}
            onChange={(e) => onCredsChange({ ...creds, tenancy_ocid: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'ocid1.tenancy.oc1...'}
          />
        </div>
        <div>
          <label className={labelClass}>User OCID *</label>
          <input
            type="text"
            value={creds.user_ocid || ''}
            onChange={(e) => onCredsChange({ ...creds, user_ocid: e.target.value })}
            className={`${inputClass} w-full px-3 py-2`}
            placeholder={hasExisting ? '••••••••••••' : 'ocid1.user.oc1...'}
          />
        </div>
      </div>
      <div>
        <label className={labelClass}>API Key Fingerprint *</label>
        <input
          type="text"
          value={creds.fingerprint || ''}
          onChange={(e) => onCredsChange({ ...creds, fingerprint: e.target.value })}
          className={`${inputClass} w-full px-3 py-2`}
          placeholder="aa:bb:cc:dd:..."
        />
      </div>
      <div>
        <label className={labelClass}>Private Key (PEM) *</label>
        <textarea
          value={creds.private_key || ''}
          onChange={(e) => onCredsChange({ ...creds, private_key: e.target.value })}
          className={`${inputClass} w-full px-3 py-2 h-24 font-mono text-xs`}
          placeholder={
            hasExisting
              ? 'Key saved. Paste new key to replace.'
              : '-----BEGIN RSA PRIVATE KEY-----\n...'
          }
        />
      </div>
      <div>
        <label className={labelClass}>Regions</label>
        <RegionChips
          regions={(config.regions as string[]) || []}
          available={ORACLE_REGIONS}
          onChange={(regions) => onConfigChange({ ...config, regions })}
        />
      </div>
    </div>
  );
}

// ── Provider Card ──

function ProviderCard({
  provider,
  integration,
  onUpdate,
  onTest,
  testing,
}: {
  provider: CloudProvider;
  integration: GlobalIntegration | undefined;
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testing: boolean;
}) {
  const meta = PROVIDER_META[provider];
  const [expanded, setExpanded] = useState(false);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, unknown>>(integration?.config || {});
  const [dirty, setDirty] = useState(false);

  const handleCredsChange = useCallback(
    (c: Record<string, string>) => {
      setCreds(c);
      setDirty(true);
    },
    []
  );

  const handleConfigChange = useCallback(
    (c: Record<string, unknown>) => {
      setConfig(c);
      setDirty(true);
    },
    []
  );

  const handleSave = useCallback(() => {
    if (!integration) return;

    // Pack credentials into auth_data JSON
    let authData: string | undefined;
    if (provider === 'gcp' && creds._raw_json) {
      authData = creds._raw_json;
    } else if (Object.values(creds).some((v) => v)) {
      const { _raw_json: _, ...cleanCreds } = creds;
      authData = JSON.stringify(cleanCreds);
    }

    const update: Record<string, unknown> = {
      auth_method: meta.authMethod,
      config,
    };
    if (authData) {
      update.auth_data = authData;
    }

    onUpdate(integration.id, update);
    setDirty(false);
  }, [integration, creds, config, meta.authMethod, onUpdate, provider]);

  const hasExisting = integration?.has_credentials || false;
  const status = integration?.status || 'not_linked';

  const FieldsComponent = {
    aws: AWSFields,
    azure: AzureFields,
    gcp: GCPFields,
    oracle: OracleFields,
  }[provider];

  return (
    <div
      className="rounded-xl border border-[#224349] bg-[#0f2023] overflow-hidden transition-all"
      style={{ borderTopColor: meta.accent, borderTopWidth: '2px' }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#0a1a1d]/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg ${meta.accentBg} flex items-center justify-center`}
          >
            <span className="material-symbols-outlined text-lg" style={{ color: meta.accent }}>
              cloud
            </span>
          </div>
          <div className="text-left">
            <div className="text-sm font-semibold text-white">{meta.displayName}</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {statusBadge(status)}
          <span className="material-symbols-outlined text-[#4a6670] text-lg transition-transform"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
          >
            expand_more
          </span>
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-[#224349]">
          <div className="pt-3">
            <FieldsComponent
              creds={creds}
              config={config}
              hasExisting={hasExisting}
              onCredsChange={handleCredsChange}
              onConfigChange={handleConfigChange}
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 mt-4 pt-3 border-t border-[#224349]/50">
            <button
              onClick={() => integration && onTest(integration.id)}
              disabled={testing}
              className="px-4 py-1.5 rounded-lg text-xs font-medium border border-[#224349] text-[#8fc3cc] hover:border-[#07b6d5] hover:text-[#07b6d5] transition-colors disabled:opacity-30"
            >
              {testing ? (
                <span className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                  Testing...
                </span>
              ) : (
                'Test Connection'
              )}
            </button>
            <button
              onClick={handleSave}
              disabled={!dirty}
              className="px-4 py-1.5 rounded-lg text-xs font-bold bg-[#07b6d5] text-[#0f2023] hover:bg-[#07b6d5]/80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Section ──

interface CloudProvidersSectionProps {
  integrations: GlobalIntegration[];
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onTest: (id: string) => Promise<void>;
  testingId: string | null;
}

const CloudProvidersSection: React.FC<CloudProvidersSectionProps> = ({
  integrations,
  onUpdate,
  onTest,
  testingId,
}) => {
  const cloudIntegrations = integrations.filter((gi) =>
    CLOUD_PROVIDERS.includes(gi.service_type as CloudProvider)
  );

  const getIntegration = (provider: CloudProvider) =>
    cloudIntegrations.find((gi) => gi.service_type === provider);

  return (
    <div className="mt-8">
      <div className="flex items-center gap-2 mb-4">
        <span className="material-symbols-outlined text-[#07b6d5]">cloud</span>
        <h3 className="text-lg font-bold text-white">Cloud Providers</h3>
      </div>
      <p className="text-sm text-[#8fc3cc] mb-4">
        Configure credentials for cloud infrastructure discovery and monitoring.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {CLOUD_PROVIDERS.map((provider) => (
          <ProviderCard
            key={provider}
            provider={provider}
            integration={getIntegration(provider)}
            onUpdate={onUpdate}
            onTest={onTest}
            testing={testingId === getIntegration(provider)?.id}
          />
        ))}
      </div>
    </div>
  );
};

export default CloudProvidersSection;
```

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to CloudProvidersSection

**Step 3: Commit**

```bash
git add frontend/src/components/Settings/CloudProvidersSection.tsx
git commit -m "feat(frontend): add CloudProvidersSection with provider-specific credential forms"
```

---

### Task 5: Wire CloudProvidersSection into IntegrationHub

**Files:**
- Modify: `frontend/src/components/Settings/IntegrationHub.tsx:21` (imports)
- Modify: `frontend/src/components/Settings/IntegrationHub.tsx:322-332` (JSX rendering)

**Step 1: Add import**

In `frontend/src/components/Settings/IntegrationHub.tsx`, after line 21:
```typescript
import GlobalIntegrationsSection from './GlobalIntegrationsSection';
```

Add:
```typescript
import CloudProvidersSection from './CloudProvidersSection';
```

**Step 2: Render CloudProvidersSection after GlobalIntegrationsSection**

Find the GlobalIntegrationsSection JSX block (lines 322-332). After the closing `/>` of `<GlobalIntegrationsSection ... />`, add:

```jsx
{/* Section 4: Cloud Provider Credentials */}
<CloudProvidersSection
  integrations={globalIntegrations}
  onUpdate={handleGlobalUpdate}
  onTest={handleTestGlobal}
  testingId={testingGlobalId}
/>
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 4: Visual verification**

Run: `cd frontend && npm run dev`
Open browser → Settings/Integrations page. Verify:
- Cloud providers no longer appear in the Global Integrations section
- New "Cloud Providers" section appears below with 4 cards (AWS, Azure, GCP, Oracle)
- Clicking a card expands to show provider-specific credential fields
- AWS: Access Key ID, Secret Access Key, Role ARN, External ID, Session Token, Regions
- Azure: Tenant ID, Client ID, Client Secret, Subscriptions
- GCP: Service Account JSON textarea, auto-detected Project ID
- Oracle: Tenancy OCID, User OCID, Fingerprint, Private Key textarea, Regions
- Each card has Test Connection and Save buttons
- Cards have colored top borders (orange/blue/blue/red)

**Step 5: Commit**

```bash
git add frontend/src/components/Settings/IntegrationHub.tsx
git commit -m "feat(frontend): wire CloudProvidersSection into IntegrationHub"
```

---

### Task 6: End-to-End Verification

**Files:** None (verification only)

**Step 1: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors (or only pre-existing errors unrelated to cloud credentials)

**Step 2: Backend import check**

Run: `cd backend && python -c "from src.integrations.profile_models import GlobalIntegration, DEFAULT_GLOBAL_INTEGRATIONS; from src.integrations.probe import GlobalProbe; print(f'{len(DEFAULT_GLOBAL_INTEGRATIONS)} integrations, GCP auth={DEFAULT_GLOBAL_INTEGRATIONS[-1][\"auth_method\"]}')"`
Expected: `10 integrations, GCP auth=gcp_sa`

**Step 3: Visual verification checklist**

Run `cd frontend && npm run dev` and check:
- [ ] Global Integrations section shows only ELK, Jira, Confluence, Remedy, GitHub (no cloud)
- [ ] Cloud Providers section shows AWS, Azure, GCP, Oracle cards in 2x2 grid
- [ ] Expanding AWS shows: Access Key ID, Secret Access Key, Role ARN, External ID (conditional), Session Token, Regions chips
- [ ] Expanding Azure shows: Tenant ID, Client ID, Client Secret, Subscriptions tags
- [ ] Expanding GCP shows: Service Account JSON textarea, Project ID (read-only, auto-detected)
- [ ] Expanding Oracle shows: Tenancy OCID, User OCID, Fingerprint, Private Key textarea, Regions chips
- [ ] Save button is disabled until fields are edited
- [ ] Test Connection button calls the backend
- [ ] Status badges update correctly (Connected / Error / Not Configured)

**Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: cloud credential form polish"
```
