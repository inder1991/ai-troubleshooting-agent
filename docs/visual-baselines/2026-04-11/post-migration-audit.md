# Post-Migration Audit — 2026-04-11

Executed as Phase 6 Task 6.4 of `2026-04-11-unified-theme-and-app-diagnostic-hardening-plan.md`. This is a static-analysis audit over `frontend/src/components`; it is not a browser-rendered visual diff. It measures whether the Phase 1–5 migration actually closed the token/theming debt its own Success Criteria claimed it would.

## Anti-Patterns Verdict — FAIL (tokens), PASS (typography)

The parent plan's Success Criteria set hard numerical gates. Against the current `main`:

| Gate | Threshold | Actual | Verdict |
|---|---|---|---|
| `bg-(slate\|gray\|zinc\|stone\|neutral)-\d` | ≤ 10 | **207 occurrences / 88 files** | ❌ FAIL (20×) |
| `text-[8-11px]` / `text-nano` / `text-micro` | ≤ 30 | **0** | ✅ PASS |
| `bg-[#` / `text-[#` / `border-[#` | 0 | **660 occurrences / 103 files** | ❌ FAIL |
| Legacy `duck-*` / `background-dark` / `neutral-slate` / `neutral-border` | (implicit 0 for 6.1) | **199 occurrences / 45 files** | ❌ blocks Task 6.1 |
| `font-display` resolves to a sans chrome | sans | Inter Tight | ✅ PASS (audit fix `eaddf3bc` + `325cb92b`) |
| HomePage feed tabs use `wr-*` tokens, not hex | yes | yes | ✅ PASS (audit fix `6d7f1bda`) |

**Bonus informational metric** — hex color *literals* in TSX string form (`'#rrggbb'`): **2,113 occurrences across 144 files**. Much of this is data/config (topology colors, chart palettes, heatmap scales) rather than chrome, so it does not all need to migrate — but the number demonstrates that the codebase has never committed to routing color decisions through a single namespace.

## Executive Summary

The unified-theme plan's Phases 1–5 shipped, but **Phase 5 polish landed on top of a codebase whose Phase 3 token migration was only partially executed**. The `wr-*` namespace exists, the shell/header/footer unification exists, and the typography is now internally consistent (after the 2026-04-11 audit fix series). But **two of the three numerical Success Criteria were never actually enforced** — arbitrary `bg-slate-*` / `text-slate-*` and `bg-[#...]` hex were never codemodded out of the 100+ non-war-room components.

This does not break the build. It does not regress the app diagnostic page (which was pixel-stable gated). But it means Phase 6 Task 6.1 ("delete legacy `duck-*` aliases") is **not executable today** — doing so would trigger ~199 Tailwind "unknown class" errors at build time.

## Detailed Findings

### Critical

**C1. Legacy alias deletion is blocked.**
`duck-*`, `background-dark/light`, `neutral-slate`, `neutral-border` are still referenced by 45 files / 199 sites — including load-bearing surfaces like `SidebarNav.tsx` (22), `AssistantDock.tsx` (14), `AgentFleetPulse.tsx` (12), `ActionCenter/forms/DatabaseDiagnosticsFields.tsx` (12), `DatabaseWarRoom.tsx` (8), and `HomePage.tsx` (6). Plan Task 6.1's precondition ("grep returns empty") is not met. **Impact:** Phase 6 cannot ship its headline cleanup commit. Requires a separate migration plan.

### High

**H1. Raw hex color classes persist throughout chrome.**
660 occurrences of `bg-[#...]` / `text-[#...]` / `border-[#...]` across 103 files. Dense in:
- `IPAMDashboard.tsx` (72), `TopologyEditor/DevicePropertyPanel.tsx` (43), `Settings/GlobalIntegrationsSection.tsx` (35), `Settings/CloudProvidersSection.tsx` (27), `IPAM/IPAMSubnetDetail.tsx` (27)
- `Investigation/AISupervisor.tsx` (20), `Settings/ClusterProfilesTable.tsx` (20), `SessionSidebar.tsx` (18), `Investigation/Investigator.tsx` (17), `Investigation/EvidenceStack.tsx` (14)

These bypass the `wr-*` token system entirely and will silently diverge from the rest of the app on any future theme shift (dark-mode-light-mode, brand repalette). **Impact:** future theming work has no single source of truth; each file must be edited individually.

**H2. Slate/gray/zinc Tailwind defaults used as chrome.**
207 occurrences / 88 files. Heaviest: `TroubleshootingUI.tsx` (9), `CICD/DeliveryDrawer.tsx` (3), `Dashboard/TimelineCard.tsx` (7), `EvidenceFindings.tsx` (7), `Dashboard/TraceCard.tsx` (5). These ignore the token system *and* ignore the project's documented neutral palette. Many are in surfaces the unified-theme plan explicitly claimed to touch (Dashboard, EvidenceFindings, CICD). **Impact:** same as H1, plus these shades look *off* against the `wr-bg-*` surfaces around them.

### Medium

**M1. `primary` token is still referenced.**
19 occurrences / 7 files (`AISupervisor.tsx` 6, `EvidenceStack.tsx` 3, `ContextScope.tsx` 3, `Investigator.tsx`, `HypothesisCard.tsx`, `RemediationProgressBar.tsx`). The plan's Task 6.1 scopes `primary` as deletable, but these callers would break. None of the files are newly introduced — all are pre-Phase-3. **Impact:** minor; `primary` still resolves to `#e09f3e` which is the correct brand amber. Can be left as-is if callers are fine with it.

**M2. `HowItWorks/*` hex leaks remain unscoped.**
Flagged during the 2026-04-11 audit fix Task 3 but explicitly deferred: `investigationFlowData.ts` (13), `ScenarioTab.tsx` (18), `InvestigationFlowTab.tsx:162`, `ArchitectureTab.tsx:10-17`. These are data constants, not chrome, but they still hard-code brand-adjacent colors.

### Low

**L1. `EnvironmentHealth.tsx:31-34`** hard-codes 4 hex colors for health-state backgrounds — 4 lines, trivially tokenizable (`wr-status-success` / `wr-status-warning` / `wr-status-error` / `wr-status-pending` already exist in the config).

**L2. `SidebarNav.tsx` imperative hover handlers** (22 `duck-*` hits include this) — previously flagged as audit Medium #2 and still deferred.

## Positive Findings

1. **Typography is internally coherent.** `font-display` and `font-sans` both resolve to Inter Tight; no serif bleed anywhere in chrome. The Phase 5 regression is fully healed.
2. **War room shell is unified.** `warroom-shell` / `warroom-header` / `warroom-column` / `warroom-footer` are used across all 4 war rooms — the Phase 2 deliverable held.
3. **`wr-*` token namespace exists and is correct.** CSS variables in `:root`, Tailwind aliases in `tailwind.config.js`, and war-room files use them consistently. The system is in place; adoption is the gap.
4. **App diagnostic page preservation contract held.** No changes landed on `InvestigationView.tsx` / `EvidenceFindings.tsx` steady-state rendering during the audit fix series.
5. **Zero sub-12px body text.** `text-micro` / `text-nano` / `text-[8-11px]` are all fully eliminated (Phase 6 Task 6.2 deletion is safe and has shipped).

## Recommendations by Priority

### Immediate (this cleanup pass)
1. **Ship Phase 6 Task 6.2** (delete `text-micro`/`text-nano`) — done as commit `6595e0b4`.
2. **Ship Phase 6 Task 6.3** (update project memory to reflect `wr-*` / Inter Tight / amber) — done via MEMORY.md edit.
3. **Do not ship Task 6.1.** Carve it out as a new plan (see Short-term).

### Short-term (next plan, 1–2 focused days)
4. **Plan: "Token migration sweep — 45 files, 199 sites."** Codemod `duck-*` → `wr-*`. Each file is a commit; each batch of ~10 files is a PR. Once at zero, delete the aliases (6.1). Success gate: `rg 'duck-' frontend/src` returns 0.

### Medium-term (follow-up plan)
5. **H1/H2 sweep:** `bg-[#...]` and `bg-slate-*` migration. Larger scope (103 + 88 files). Do per-module batches — IPAM first (densest), then Settings, then Investigation, then Dashboard. Each batch has its own success criteria and smoke test. Explicitly skip chart/topology data colors (they belong in data, not Tailwind classes).

### Long-term / monitoring
6. **Add a pre-commit check** that forbids net-new `bg-[#` / `text-[#` / `duck-*` / `bg-slate-` introductions in `frontend/src/components`. Without a lint fence, any future work immediately reaccumulates debt.
7. **60-day checkpoint on `font-editorial` usage** (2026-06-10). If still zero call sites, drop the utility and the Fraunces Google Fonts param to reclaim ~30KB idle.

## Suggested Commands / Skills for Fixes

- **Codemod for Task 6.1 / H1 / H2:** write a small `jscodeshift` or regex-based Node script — these substitutions are mechanical and do not need LLM reasoning.
- **`/impeccable:normalize`** for the per-module sweeps once call-site lists are extracted.
- **`/impeccable:audit`** again after the token migration plan lands, to re-verify Success Criteria.

## Comparison to Parent-Plan Success Criteria

| Criterion | Status |
|---|---|
| `bg-(slate\|gray\|…)-\d` ≤ 10 | ❌ 207 |
| `text-(nano\|micro\|[8-11]px)` ≤ 30 | ✅ 0 |
| `bg-[#…]` / `text-[#…]` = 0 | ❌ 660 |
| App diagnostic screenshot stability | ✅ (no changes to steady state) |
| Every preserved panel present and functional | ⚠️ unverified (no browser run in this audit) |
| All 4 war rooms share shell chrome | ✅ |
| `/impeccable:audit` anti-pattern verdict: PASS | ❌ FAIL on tokens, PASS on typography |
| Fraunces headlines + Inter Tight body site-wide | ⚠️ partial — Fraunces is loaded but *intentionally* dormant after the audit fix; this criterion was superseded |
| Hover depth + entrance animation on non-diagnostic pages | ✅ (Phase 5.4/5.5) |

**Bottom line:** the plan's *visual* goals mostly landed; its *tokenization* goals did not. The cleanup phase as originally written cannot close.
