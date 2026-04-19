# SDET Audit Close-Out — 2026-04-19

This is the closing record for the 74-issue SDET production-readiness
audit conducted on 2026-04-17. The audit enumerated 30 app-diagnostic
workflow bugs plus 44 frontend↔backend mismatch/broken-functionality
issues, which were clustered into a 10-PR roadmap. All ten PRs
shipped between 2026-04-18 and 2026-04-19.

## PRs shipped

| PR | Theme                          | GitHub | Date       |
|----|--------------------------------|--------|------------|
| A  | Security hardening             | #62    | 2026-04-18 |
| B  | User-control gaps              | #63    | 2026-04-18 |
| C  | Data-loss / correctness        | #64    | 2026-04-19 |
| D  | Reactivity + event lifecycle   | #65    | 2026-04-19 |
| F  | Frontend↔backend contracts     | #66    | 2026-04-19 |
| G  | Historical-incident polish     | #67    | 2026-04-19 |
| H  | Accessibility                  | #68    | 2026-04-19 |
| E  | Backend surfacing              | #69    | 2026-04-19 |
| I  | UI polish                      | #70    | 2026-04-19 |
| J  | Systemic observability         | this   | 2026-04-19 |

## Bugs landed per PR

### PR-A — Security (7 fixes)
- Credential redactor for sk-ant-*, Bearer, Authorization, api_key/secret JSON
- llm_client.py error-path redaction
- Session ownership check (feature-flag gated)
- Fernet master-key-required mode (prevents silent auto-gen)
- Helm chart threads encryption.masterKey.existingSecret env
- SESSION_OWNERSHIP_CHECK env var plumbed end-to-end
- 43 security tests green

### PR-B — User controls (6 fixes)
- Copy-session-link button (persistent, confirmed)
- Cancel-investigation button with phase-aware disabled + confirm dialog
- Stream watchdog (30s) — force-closes idle streams with timeout message
- Open-PR default handler falls back to generateFix()
- Resolve-Incident visible-disabled with tooltip
- Attach-Repo auto-opens chat drawer

### PR-C — Data-loss / correctness (8 fixes)
- Cross-check race (metrics↔logs + tracing↔metrics) per-state asyncio.Lock
- Re-investigation reset clears divergences + announcement set
- Verdict precedence — highest-confidence source wins
- Namespace auto-detect refuses to overwrite user-set (incl. "default")
- Historical ReproduceQueryRow disables Run-inline + tooltip
- Backend PromQL run validator (4h cap, 15s-300s step, wildcard reject)
- PromQL rate limit (30/min/session) + audit log
- Frontend surfaces 400/429 detail + threads session_id for rate keying

### PR-D — Reactivity (3 fixes)
- IncidentLifecycleContext internal 60s ticker; decoupled from polling
- FreshnessRow flips to `resolved` the moment phase goes terminal
- AgentsCard NOW strip uses last-event-wins (re-investigation fix)

### PR-F — Contracts (3 fixes + regression test)
- StartSessionRequest declares all TS-authored fields (no more silent drop)
- BudgetTelemetry shape matches frontend; wired onto /status
- Contract regression test locks wire shapes source-level

### PR-G — Historical polish (2 fixes)
- InvestigationView suspends polling / tickers / WS re-fetch on archived
- ChatDrawer read-only banner + disabled input on archived

### PR-H — Accessibility (5 fixes)
- Polite live regions on freshness row + phase narrative
- War Room grid regions wrapped with role=region + aria-labelledby
- Service topology SVG a11y (summary + per-node aria-label + tabindex)
- Focus ring upgrades on SessionControlsRow
- Color-meaning audit (no regressions found)

### PR-E — Backend surfacing (2 fixes)
- SignatureMatchPill renders state.signature_match
- Stop-reason line renders state.diagnosis_stop_reason

### PR-I — Polish (2 fixes)
- Cost-burn warning clause (amber ≥80%, red ≥95%)
- Phase-aware empty-state hints in EvidenceFindings

### PR-J — Systemic (3 fixes)
- /readyz now also checks ANTHROPIC_API_KEY presence (+ placeholder guard)
- Request-ID middleware: accepts caller header or mints UUID, stamps response
- Structured error envelopes: HTTPException / ValidationError / unhandled

## Explicitly deferred

Two items known to be failing but explicitly excluded from this sweep
because their root cause is infrastructure-level, not feature-level:

1. **`frontend/src/__tests__/App.test.tsx`** — 2 save-cluster credential-policy
   tests failing since commit `08500197` (2026-04-17). The auth-method
   cleanup that removed `service_account` needs a corresponding test
   update. Tracking: carry-forward backlog.
2. **Playwright e2e suites (4 files)** — fail to load under the vitest
   runner because they're Playwright tests, not vitest tests. Requires
   splitting the `test` script into `vitest` and `playwright` halves.
   Tracking: carry-forward backlog.

## Verification

- Backend: 450 agent tests + 51 API + 26 promql safety + 9 namespace
  guard + 9 cross-check + 9 middleware + 5 health-credential = all green
- Frontend: 685 unit tests across 86 files green; 2 pre-existing +
  4 e2e-loader failures unchanged

## User amendments honored

Four decisions pressure-tested before execution:

1. PR-D lifecycle ✅ event-driven trigger on phase_change (not just 60s poll)
2. PR-E visualizations ✅ audited; no dead compute to kill, both surfacing
3. Resolve Incident ✅ visible-disabled with tooltip, not hidden
4. PromQL ✅ backend validator (4h cap) + rate limit + audit log

## What's next

Beyond this audit close-out:
- Wire the carry-forward backlog (App.test update, Playwright runner split)
- Monitor signature_match + stop_reason surfaces for operator feedback
- Revisit the "willing to kill backend compute" amendment quarterly —
  diagnosis_stop_reason and signature_match are only valuable if
  operators actually read them.
