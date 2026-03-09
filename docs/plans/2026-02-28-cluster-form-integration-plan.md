# Cluster Form Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the cluster diagnostics form auto-populate from Integration Hub profiles, support inline cluster creation with "Save this cluster" option, add kubeconfig file upload, and wire credentials through to the backend.

**Architecture:** Frontend form redesign with two modes (profile-selected vs manual-entry), optional inline profile creation via existing `/api/v5/profiles` endpoint, backend `StartSessionRequest` extended with auth fields, `connection_config` wired through to cluster client factory.

**Tech Stack:** React + TypeScript (frontend), Python FastAPI + Pydantic (backend), existing profileApi.ts + CredentialResolver

---

### Task 1: Add auth fields to StartSessionRequest and type definitions

**Files:**
- Modify: `backend/src/api/models.py:65-76`
- Modify: `frontend/src/types/index.ts:545-554`
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cluster_routing.py`:

```python
class TestStartSessionAuthFields:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_accepts_auth_fields(self, mock_build, mock_run, client):
        """POST /session/start accepts authToken and authMethod for cluster sessions."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
            "auth_token": "eyJhbGciOi...",
            "auth_method": "token",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestStartSessionAuthFields -v`
Expected: FAIL — Pydantic rejects unknown fields (or silently ignores them, test may pass; if so, the test is a baseline)

**Step 3: Add fields to StartSessionRequest**

In `backend/src/api/models.py`, add after `capability` field (line 76):

```python
    authToken: Optional[str] = Field(default=None, alias="auth_token")
    authMethod: Optional[str] = Field(default=None, alias="auth_method")
```

**Step 4: Add fields to frontend ClusterDiagnosticsForm type**

In `frontend/src/types/index.ts`, add to `ClusterDiagnosticsForm` (after line 553):

```typescript
export interface ClusterDiagnosticsForm {
  capability: 'cluster_diagnostics';
  cluster_url: string;
  namespace?: string;
  symptoms?: string;
  auth_token?: string;
  auth_method?: 'token' | 'kubeconfig';
  resource_type?: string;
  profile_id?: string;
  save_cluster?: boolean;
  cluster_name?: string;
}
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestStartSessionAuthFields -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/models.py frontend/src/types/index.ts backend/tests/test_cluster_routing.py
git commit -m "feat: add authToken and authMethod fields to StartSessionRequest"
```

---

### Task 2: Wire connection_config into cluster session creation

**Files:**
- Modify: `backend/src/api/routes_v4.py:162-194`
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_cluster_routing.py`:

```python
class TestClusterConnectionConfig:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_stores_connection_config(self, mock_build, mock_run, client):
        """Cluster session stores connection_config in session dict."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
            "auth_token": "test-token-123",
            "auth_method": "token",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert "connection_config" in session

    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_no_creds_no_profile_returns_422(self, mock_build, mock_run, client):
        """Cluster session with no credentials and no profile returns 422."""
        mock_build.return_value = MagicMock()
        # Patch resolve_active_profile to return None (no profile found)
        with patch("src.api.routes_v4.resolve_active_profile", return_value=None):
            resp = client.post("/api/v4/session/start", json={
                "service_name": "Cluster Diagnostics",
                "capability": "cluster_diagnostics",
                "cluster_url": "https://api.cluster.example.com",
            })
            # Should still succeed because cluster_url is provided (just no auth)
            # Only reject if no cluster_url at all
            assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestClusterConnectionConfig -v`
Expected: FAIL — `connection_config` not in session dict

**Step 3: Implement connection_config wiring and cluster client factory**

In `backend/src/api/routes_v4.py`, add the factory function before `start_session` (around line 135):

```python
def create_cluster_client(connection_config=None):
    """Factory for cluster client. Returns MockClusterClient for now; swappable for real client."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    return MockClusterClient(platform="openshift")
```

Then replace the cluster diagnostics block in `start_session()` (lines 162-194):

```python
    # ── Cluster Diagnostics capability ──
    if capability == "cluster_diagnostics":
        # Build connection config: prefer profile, fall back to ad-hoc fields
        if not connection_config and request.clusterUrl:
            # Ad-hoc mode: build minimal config from request fields
            try:
                from src.integrations.connection_config import ResolvedConnectionConfig
                connection_config = ResolvedConnectionConfig(
                    cluster_url=request.clusterUrl,
                    cluster_token=request.authToken or "",
                    cluster_type="kubernetes",
                )
            except Exception as e:
                logger.warning("Could not build ad-hoc connection config: %s", e)

        cluster_client = create_cluster_client(connection_config)
        graph = build_cluster_diagnostic_graph()

        sessions[session_id] = {
            "service_name": request.serviceName or "Cluster Diagnostics",
            "incident_id": incident_id,
            "phase": "initial",
            "confidence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "emitter": emitter,
            "state": None,
            "profile_id": profile_id,
            "capability": "cluster_diagnostics",
            "graph": graph,
            "chat_history": [],
            "connection_config": connection_config,
        }

        background_tasks.add_task(
            run_cluster_diagnosis, session_id, graph, cluster_client, emitter
        )

        logger.info("Cluster session created", extra={"session_id": session_id, "action": "session_created", "extra": "cluster_diagnostics"})

        return StartSessionResponse(
            session_id=session_id,
            incident_id=incident_id,
            status="started",
            message="Cluster diagnostics started",
            service_name=request.serviceName or "Cluster Diagnostics",
            created_at=sessions[session_id]["created_at"],
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_cluster_routing.py::TestClusterConnectionConfig -v`
Expected: PASS

**Step 5: Run full backend test suite**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat: wire connection_config into cluster session with client factory"
```

---

### Task 3: Redesign ClusterDiagnosticsFields — profile credential badge + override

**Files:**
- Modify: `frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx`

**Step 1: Implement the profile credential badge and override UX**

Replace the entire `ClusterDiagnosticsFields.tsx` with the redesigned version. Key changes:

1. Add `overrideAuth` state to track when user wants to manually enter creds despite having a profile
2. When profile selected AND `profile.has_cluster_credentials === true`:
   - Hide auth section (Cluster URL, Auth Method, Auth Token)
   - Show green badge: "Credentials stored" + "Override" link
3. When "Override" clicked, show auth fields with "Use stored" revert link
4. When no profile selected, show all fields (existing behavior)

```tsx
import React, { useState, useEffect } from 'react';
import type { ClusterDiagnosticsForm } from '../../../types';
import type { ClusterProfile } from '../../../types/profiles';
import { listProfiles } from '../../../services/profileApi';

interface ClusterDiagnosticsFieldsProps {
  data: ClusterDiagnosticsForm;
  onChange: (data: ClusterDiagnosticsForm) => void;
}

const namespaces = ['default', 'kube-system', 'monitoring', 'production', 'staging'];
const resourceTypes = ['All Resources', 'Pods', 'Deployments', 'Services', 'StatefulSets', 'DaemonSets', 'Nodes'];

const envBadge: Record<string, string> = {
  prod: 'text-red-400',
  staging: 'text-[#07b6d5]',
  dev: 'text-emerald-400',
};

const statusDot: Record<string, string> = {
  connected: 'bg-green-500',
  warning: 'bg-amber-500',
  unreachable: 'bg-red-500',
  pending_setup: 'bg-gray-500',
};

const ClusterDiagnosticsFields: React.FC<ClusterDiagnosticsFieldsProps> = ({ data, onChange }) => {
  const [profiles, setProfiles] = useState<ClusterProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>(data.profile_id || '');
  const [overrideAuth, setOverrideAuth] = useState(false);

  useEffect(() => {
    listProfiles()
      .then(setProfiles)
      .catch(() => {});
  }, []);

  const activeProfile = profiles.find((p) => p.id === selectedProfile);
  const hasStoredCreds = activeProfile?.has_cluster_credentials ?? false;
  const showAuthSection = !selectedProfile || overrideAuth || !hasStoredCreds;

  const handleProfileSelect = (profileId: string) => {
    setSelectedProfile(profileId);
    setOverrideAuth(false);
    if (profileId) {
      const profile = profiles.find((p) => p.id === profileId);
      if (profile) {
        onChange({
          ...data,
          profile_id: profileId,
          cluster_url: profile.cluster_url,
          auth_method: 'token',
          auth_token: undefined,
        });
      }
    } else {
      onChange({ ...data, profile_id: undefined });
    }
  };

  const update = (field: Partial<ClusterDiagnosticsForm>) => {
    onChange({ ...data, ...field });
  };

  return (
    <div className="space-y-4">
      {/* Select Cluster Profile */}
      {profiles.length > 0 && (
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium">Select Cluster Profile</label>
          <select
            value={selectedProfile}
            onChange={(e) => handleProfileSelect(e.target.value)}
            className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
          >
            <option value="">-- Manual Entry --</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} [{p.environment}] {p.status === 'connected' ? '' : `(${p.status})`}
              </option>
            ))}
          </select>
          {selectedProfile && activeProfile && (
            <div className="flex items-center gap-2 mt-1.5 text-[10px]">
              <span className={`w-1.5 h-1.5 rounded-full ${statusDot[activeProfile.status] || 'bg-gray-500'}`} />
              <span className={envBadge[activeProfile.environment] || 'text-gray-400'}>{activeProfile.environment}</span>
              <span className="text-gray-600 font-mono">{activeProfile.cluster_url}</span>
              {hasStoredCreds && !overrideAuth && (
                <>
                  <span className="material-symbols-outlined text-green-500 text-[12px]">shield</span>
                  <span className="text-green-500">Credentials stored</span>
                  <button
                    type="button"
                    onClick={() => setOverrideAuth(true)}
                    className="text-[#07b6d5] hover:underline ml-1"
                  >
                    Override
                  </button>
                </>
              )}
              {overrideAuth && (
                <>
                  <span className="text-amber-400">Using manual credentials</span>
                  <button
                    type="button"
                    onClick={() => {
                      setOverrideAuth(false);
                      update({ auth_token: undefined });
                    }}
                    className="text-[#07b6d5] hover:underline ml-1"
                  >
                    Use stored
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Auth Section — hidden when profile has stored credentials (unless override) */}
      {showAuthSection && (
        <>
          {/* Cluster API URL */}
          {!selectedProfile && (
            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-medium">
                Cluster API URL <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={data.cluster_url}
                onChange={(e) => update({ cluster_url: e.target.value })}
                className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
                placeholder="https://api.cluster.example.com:6443"
                required
              />
            </div>
          )}

          {/* Auth Method Toggle */}
          <div>
            <label className="block text-xs text-gray-400 mb-2 font-medium">Auth Method</label>
            <div className="grid grid-cols-2 gap-2">
              {(['token', 'kubeconfig'] as const).map((method) => {
                const active = (data.auth_method || 'token') === method;
                return (
                  <button
                    key={method}
                    type="button"
                    onClick={() => update({ auth_method: method })}
                    className={`px-3 py-2 rounded-lg border text-xs font-medium transition-all ${
                      active
                        ? 'bg-[#07b6d5]/10 border-[#07b6d5]/30 text-[#07b6d5]'
                        : 'bg-[#0f2023] border-[#224349] text-gray-400 hover:text-gray-300'
                    }`}
                  >
                    {method === 'token' ? 'Auth Token' : 'Kubeconfig'}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Auth Token / Kubeconfig */}
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium">
              {(data.auth_method || 'token') === 'token' ? 'Bearer Token' : 'Kubeconfig Contents'}
            </label>
            <textarea
              value={data.auth_token || ''}
              onChange={(e) => update({ auth_token: e.target.value || undefined })}
              rows={3}
              className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors font-mono resize-none"
              placeholder={
                (data.auth_method || 'token') === 'token'
                  ? 'eyJhbGciOi...'
                  : 'Paste kubeconfig YAML...'
              }
            />
            {/* Kubeconfig file upload */}
            {(data.auth_method || 'token') === 'kubeconfig' && (
              <label className="flex items-center gap-1.5 mt-1.5 cursor-pointer text-[10px] text-[#07b6d5] hover:text-[#07b6d5]/80 transition-colors">
                <span className="material-symbols-outlined text-[14px]">upload_file</span>
                <span>Upload .kubeconfig</span>
                <input
                  type="file"
                  accept=".yaml,.yml,.kubeconfig"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onload = (ev) => {
                        const contents = ev.target?.result as string;
                        if (contents) update({ auth_token: contents });
                      };
                      reader.readAsText(file);
                    }
                    e.target.value = '';
                  }}
                />
              </label>
            )}
          </div>
        </>
      )}

      {/* Save This Cluster — only shown in manual entry mode (no profile selected) */}
      {!selectedProfile && (
        <div className="border border-[#224349] rounded-lg p-3 bg-[#0f2023]/50">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={data.save_cluster ?? true}
              onChange={(e) => update({ save_cluster: e.target.checked })}
              className="w-3.5 h-3.5 rounded border-[#224349] bg-[#0f2023] text-[#07b6d5] focus:ring-[#07b6d5]/30"
            />
            <span className="text-xs text-gray-300">Save this cluster for future diagnostics</span>
          </label>
          {(data.save_cluster ?? true) && (
            <input
              type="text"
              value={data.cluster_name || ''}
              onChange={(e) => update({ cluster_name: e.target.value })}
              className="w-full mt-2 px-3 py-2 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
              placeholder="Cluster name (e.g. prod-east-1)"
            />
          )}
        </div>
      )}

      {/* Target Namespace */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Target Namespace</label>
        <select
          value={data.namespace || ''}
          onChange={(e) => update({ namespace: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
        >
          <option value="">All Namespaces</option>
          {namespaces.map((ns) => (
            <option key={ns} value={ns}>
              {ns}
            </option>
          ))}
        </select>
      </div>

      {/* Resource Type */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Resource Type</label>
        <select
          value={data.resource_type || ''}
          onChange={(e) => update({ resource_type: e.target.value || undefined })}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors"
        >
          <option value="">All Resources</option>
          {resourceTypes.filter((r) => r !== 'All Resources').map((rt) => (
            <option key={rt} value={rt.toLowerCase()}>
              {rt}
            </option>
          ))}
        </select>
      </div>

      {/* Symptoms */}
      <div>
        <label className="block text-xs text-gray-400 mb-1.5 font-medium">Symptoms Description</label>
        <textarea
          value={data.symptoms || ''}
          onChange={(e) => update({ symptoms: e.target.value || undefined })}
          rows={2}
          className="w-full px-3 py-2.5 bg-[#0f2023] border border-[#224349] rounded-lg text-sm text-white placeholder-gray-600 focus:border-[#07b6d5] focus:outline-none focus:ring-1 focus:ring-[#07b6d5]/30 transition-colors resize-none"
          placeholder="Describe the observed symptoms..."
        />
      </div>
    </div>
  );
};

export default ClusterDiagnosticsFields;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Verify build succeeds**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx
git commit -m "feat: redesign cluster form with credential badge, override, and file upload"
```

---

### Task 4: Add inline profile creation + ad-hoc auth in App.tsx submit handler

**Files:**
- Modify: `frontend/src/App.tsx:233-248` (handleFormSubmit cluster branch)

**Step 1: Update the cluster submit handler to support save + ad-hoc**

In `frontend/src/App.tsx`, replace the cluster diagnostics branch in `handleFormSubmit` (lines 233-248):

```tsx
        } else if (data.capability === 'cluster_diagnostics') {
          const clusterData = data as ClusterDiagnosticsForm;
          let profileId = clusterData.profile_id;

          // Inline profile creation if "Save this cluster" is checked and no profile selected
          if (!profileId && (clusterData.save_cluster ?? true) && clusterData.cluster_url) {
            try {
              const { createProfile } = await import('./services/profileApi');
              const newProfile = await createProfile({
                name: clusterData.cluster_name || new URL(clusterData.cluster_url).hostname,
                cluster_url: clusterData.cluster_url,
                cluster_type: 'kubernetes',
                environment: 'prod',
                auth_method: clusterData.auth_method || 'token',
                auth_credential: clusterData.auth_token || '',
              });
              profileId = newProfile.id;
              addToast('Cluster saved to profiles', 'success');
            } catch (err) {
              console.warn('Failed to save cluster profile:', err);
              addToast('Could not save profile — proceeding with one-time credentials', 'warning');
            }
          }

          const session = await startSessionV4({
            service_name: 'Cluster Diagnostics',
            time_window: '1h',
            namespace: clusterData.namespace || '',
            cluster_url: clusterData.cluster_url,
            capability: 'cluster_diagnostics',
            profile_id: profileId,
            // Ad-hoc auth fields (used when no profile)
            ...((!profileId && clusterData.auth_token) ? {
              auth_token: clusterData.auth_token,
              auth_method: clusterData.auth_method || 'token',
            } : {}),
          });
          setSessions((prev) => [session, ...prev]);
          setActiveSession(session);
          setCurrentPhase(session.status);
          setConfidence(session.confidence);
          setViewState('cluster-diagnostics');
          refreshStatus(session.session_id);
```

Note: `addToast` is available from `useToast()` which is already in scope in `AppInner`. If not destructured yet, add: `const { addToast } = useToast();` near the top of `AppInner`.

**Step 2: Add auth fields to the startSessionV4 request type**

In `frontend/src/services/api.ts`, check if `StartSessionRequest` type includes `auth_token` and `auth_method`. The function uses `Record`-style typing so any fields pass through. No change needed if using `JSON.stringify(request)`.

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Verify build succeeds**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add inline profile creation and ad-hoc auth on cluster form submit"
```

---

### Task 5: Update form validation in CapabilityForm.tsx

**Files:**
- Modify: `frontend/src/components/ActionCenter/CapabilityForm.tsx:81-83`

**Step 1: Update the isValid check for cluster_diagnostics**

Replace the cluster validation (lines 81-83):

```tsx
      case 'cluster_diagnostics': {
        const cd = formData as ClusterDiagnosticsForm;
        const hasUrl = cd.cluster_url.trim().length > 0 && /^https?:\/\/.+/.test(cd.cluster_url.trim());
        const hasProfile = !!cd.profile_id;
        const hasAuth = hasProfile || !!cd.auth_token;
        const hasName = !cd.save_cluster || cd.save_cluster === false || !!cd.cluster_name?.trim();
        return hasUrl && hasAuth && hasName;
      }
```

This enforces:
- Cluster URL must be valid (always required)
- Auth required: either via profile or manual entry
- Cluster name required when "Save this cluster" is checked

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ActionCenter/CapabilityForm.tsx
git commit -m "feat: update cluster form validation for auth and save requirements"
```

---

### Task 6: Full verification

**Step 1: Run backend tests**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: All pass, 0 failures

**Step 2: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Run frontend build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit any remaining fixes**

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | models.py, types/index.ts, tests | Add `authToken`, `authMethod` to request model + `save_cluster`, `cluster_name` to frontend type |
| 2 | routes_v4.py, tests | Wire `connection_config` into cluster session, add `create_cluster_client()` factory, ad-hoc config fallback |
| 3 | ClusterDiagnosticsFields.tsx | Redesign: credential badge, override link, kubeconfig file upload, save checkbox |
| 4 | App.tsx | Inline profile creation on submit, ad-hoc auth passthrough, toast feedback |
| 5 | CapabilityForm.tsx | Update validation: require auth (profile or manual), require name when saving |
| 6 | — | Full verification (tests + tsc + build) |
