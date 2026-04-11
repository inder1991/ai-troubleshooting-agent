# CI/CD Integration — Manual Smoke Verification Checklist

> Phase A read-path for Jenkins + Argo CD + Live Board (plan: `docs/plans/2026-04-10-cicd-integration.md`).
> Run this after a full backend + frontend deploy to a staging cluster that has at least one Jenkins instance, one Argo CD instance, and a GitHub integration reachable.

## Pre-flight

- [ ] Worktree/branch built cleanly: `cd backend && pytest backend/tests/integrations/cicd -q` passes.
- [ ] `cd frontend && npx tsc --noEmit` produces no errors originating in `frontend/src/components/CICD/**` or `frontend/src/components/Home/DeliveryPulse.tsx`.
- [ ] `backend/src/api/routes_v4.py` registers `/api/v4/cicd/stream` and `/api/v4/cicd/commit/{owner}/{repo}/{sha}`.
- [ ] At least one `ClusterProfile` is marked active in the Cluster Profiles table.

## 1. Settings — Add Jenkins + Argo CD instances

Open **Settings → Global Integrations** (`/settings`).

- [ ] "Add Integration" dropdown shows **Jenkins** and **Argo CD** alongside ELK / Jira / GitHub.
- [ ] Selecting Jenkins auto-switches Auth Method to **Basic Auth**; username/password fields render.
- [ ] Selecting Argo CD auto-switches Auth Method to **Bearer Token**; token field renders.
- [ ] For both types, a "Linked clusters (comma-separated profile IDs; blank = all)" input appears below the URL field.
- [ ] Add a Jenkins instance named `ci-prod` with URL, `username:token`, and cluster_ids = active profile id. Click **Add** — a new card appears.
- [ ] Add an Argo CD instance named `cd-prod` with URL, bearer token, and cluster_ids = active profile id. Card appears.
- [ ] On each card, the cluster_ids editor shows chips and lets you add/remove ids inline. Changes persist after refresh.
- [ ] Click **Test Connection** on each card — status flips to **Connected** (green dot) or **Conn. Error** with latency/error text.

## 2. Backend — Stream endpoint smoke

```bash
CLUSTER_ID=<your active profile id>
SINCE=$(date -u -v-2H +"%Y-%m-%dT%H:%M:%SZ")   # mac; linux use -d
curl -sS "http://localhost:8000/api/v4/cicd/stream?cluster_id=$CLUSTER_ID&since=$SINCE&limit=50" | jq '{count: (.items|length), server_ts, errs: (.source_errors|length)}'
```

- [ ] HTTP 200.
- [ ] `count` > 0 when Jenkins/Argo CD have activity in window (or `0` in a quiet env — that is fine).
- [ ] `server_ts` is a recent ISO timestamp.
- [ ] `source_errors` is `[]` when everything resolves, or non-empty with `{name, source, message}` entries when a mis-configured instance is present.
- [ ] Each item has `kind`, `source`, `source_instance`, `status`, `title`, `timestamp`, `url`.
- [ ] `kind: "build"` items originate from jenkins and have `duration_s` populated when finished.
- [ ] `kind: "sync"` items originate from argocd with health-derived status.

## 3. Backend — Commit endpoint smoke

```bash
OWNER=<org>
REPO=<repo>
SHA=<a known SHA in that repo>
curl -sS "http://localhost:8000/api/v4/cicd/commit/$OWNER/$REPO/$SHA" | jq '{sha: .commit_sha, message: (.message[0:60]), files: (.files|length)}'
```

- [ ] HTTP 200 for a real SHA; fields `commit_sha`, `message`, `author`, `files` populated.
- [ ] HTTP 404 for a non-existent SHA.
- [ ] HTTP 401 when the GitHub integration token is missing / invalid.
- [ ] Each file entry has `filename`, `status`, `additions`, `deletions`, and (usually) `patch`.
- [ ] `patch` is truncated to ~1500 chars for oversized files.

## 4. Frontend — Delivery Live Board (`/cicd`)

Navigate via the sidebar **Delivery** entry (rocket icon).

- [ ] Page header reads "Delivery" with the active cluster's display name as subtitle.
- [ ] Green pulsing dot + "Last updated HH:MM:SS" updates every 10s (watch for ~20s to confirm polling).
- [ ] Filter chip bar shows Commit/Build/Sync and Success/Failed/In Progress/Healthy/Degraded chips, plus a search input.
- [ ] Toggling a Commit chip hides non-commit rows; re-toggle restores.
- [ ] Typing in search filters by title/repo (case-insensitive).
- [ ] Clear button appears only when a filter is active and resets everything.
- [ ] Source errors banner (amber) renders at the top when the backend returns `source_errors`.
- [ ] Empty state renders "No delivery events match the current filters." when filters exclude everything.
- [ ] Each row shows kind pill (color-coded), source label, title, author, target, duration (when set), SplitFlapCell status, timestamp.
- [ ] Watching a row whose status transitions (e.g. `in_progress` → `success`) shows the **flip animation** on the status cell.
- [ ] Clicking a row opens the **DeliveryDrawer** (right side).
- [ ] Drawer **Commit** tab lists metadata (kind, source, author, sha, repo, target, duration, timestamp) with a clickable external URL.
- [ ] Drawer **Diff** tab on a commit row loads via `/api/v4/cicd/commit/...` and renders filename headers, status chips, `+/-` counts, and patches.
- [ ] Drawer **Diff** tab on build/sync rows shows "Diff is only available for commits."
- [ ] Drawer **Related** tab shows placeholder text.
- [ ] Escape key closes the drawer.
- [ ] On build/sync rows, clicking **Investigate** (not the row itself) navigates to `/action-center?capability=troubleshoot_pipeline&...` without also firing the row select.

## 5. Frontend — Home Delivery Pulse widget

Navigate to **Home** (`/`).

- [ ] In the right-hand column, a "Delivery Pulse" panel sits between Recent Findings and Weekly Stats.
- [ ] Shows up to 8 recent events with kind icon, truncated title, and status chip.
- [ ] Refreshes every 15s.
- [ ] Clicking a row OR the header "Open →" navigates to `/cicd`.
- [ ] No active cluster → "No active cluster." message.
- [ ] Empty 6h window → "No recent activity."

## 6. Agents — troubleshoot_pipeline capability

- [ ] Action Center capability list includes `troubleshoot_pipeline`.
- [ ] Starting a session with capability `troubleshoot_pipeline`, cluster_id, and a `git_repo` hint returns an active V4 session with PipelineAgent engaged.
- [ ] Assistant JSON schema for `start_investigation` accepts `"troubleshoot_pipeline"` as a capability value.

## 7. ChangeAgent pre-fetch

- [ ] Start a normal `troubleshoot_app` session on a namespace that matches a recent Jenkins target.
- [ ] Inspect session context — `ci_cd_events` key is present with the deploy events intersecting incident window.
- [ ] With Jenkins/Argo CD disabled for the active cluster, the same flow omits `ci_cd_events` without raising.

## 8. Audit log

- [ ] SQLite audit table contains rows with `entity_type = "integration_cicd"` and `action` starting with `read:` after running the stream endpoint and investigating a session.
- [ ] Audit failures (e.g., read-only FS) are logged as warnings but do not crash the client call.

## 9. Regression guards

- [ ] `pytest backend/tests/integrations/cicd -q` — all green.
- [ ] `pytest backend/tests/agents/test_change_agent.py -q` — all green.
- [ ] `pytest backend/tests/api/test_routes_v4_cicd*.py -q` — all green.
- [ ] `npx tsc --noEmit` on frontend — no new errors in `CICD/**`, `Home/DeliveryPulse.tsx`, `Settings/GlobalIntegrationsSection.tsx`, `pages/CICDPage.tsx`, `router.tsx`, `contexts/NavigationContext.tsx`, `services/api.ts`, `types/index.ts`.

## Sign-off

- Tester: ______________________
- Date: ________________________
- Build SHA: ___________________
- Notes:
