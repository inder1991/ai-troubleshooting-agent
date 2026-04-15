# Home Page Audit Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reverse the Phase 5 typography regression that broke the home page and sidebar, without re-opening the broader Phase 5 visual polish.

**Architecture:** One-line Tailwind config revert of the `font-display` utility alias, plus a small token cleanup on two hard-coded tab color sites surfaced by the same audit. No component restructuring. Fraunces stays *loaded* but is no longer wired to any utility class; a new `font-editorial` utility is added for future deliberate use.

**Tech Stack:** Tailwind 3.4, Vite, TypeScript, React. No new dependencies.

**Scope boundary:** This plan addresses **audit findings only**. The separate `/impeccable:critique` recommendations (demote right rail, strip feed chrome, etc.) are out of scope and tracked separately.

---

## Context

Phase 5 commit `08e070ef` reassigned `fontFamily.display` in `tailwind.config.js` from DM Sans → Fraunces. The `font-display` Tailwind utility is used 86 times across 40 files, so every previously-sans chrome surface flipped to serif on that commit. The user reports sidebar labels rendering in a serif while center content renders in sans, plus vertical overflow on the home page (a knock-on effect of wider glyph metrics).

### Root cause location
- `frontend/tailwind.config.js:71-75` — the `fontFamily.display` block

### Downstream affected call sites (for smoke verification only — not modified)
- `frontend/src/components/Layout/SidebarNav.tsx` — 6 usages (brand, nav labels, user card)
- `frontend/src/components/Home/HomePage.tsx` — 3 usages (search input, feed tabs)
- `frontend/src/components/Investigation/EvidenceFindings.tsx` — 13 usages
- `frontend/src/components/Investigation/DatabaseWarRoom.tsx` — 6 usages
- 36 more components (`rg font-display frontend/src` for the full list)

### Medium-severity cleanup (same commit)
- `frontend/src/components/Home/HomePage.tsx:124-126, 135-137` — feed tab buttons inline `style={{ color: 'white' | '#94a3b8', borderBottom: '2px solid #e09f3e' }}`. These bypass the token system and were flagged in the audit as Medium #1.

### Out of scope
- `SidebarNav` imperative hover handlers (audit Medium #2) — touches 3 large blocks, deserves its own plan.
- Any `font-display` → `font-sans` call site migration. The revert makes the class name semantically correct again; no call site edits needed.
- `MetricStrip` / `status-aurora` / right-rail demotion (critique recommendations).
- Font loading for Fraunces in `index.html` — intentionally kept. Cost is ~30KB idle and the critique may still want it for an editorial moment.

---

## Task 1: Revert `fontFamily.display` to a sans stack, add `fontFamily.editorial` for future use

**Files:**
- Modify: `frontend/tailwind.config.js:71-75`

**Step 1: Open the file and locate the `fontFamily` block**

Current state (lines 71-75):
```js
fontFamily: {
  display: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
  sans: ['"Inter Tight"', 'Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
  mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
},
```

**Step 2: Replace with**

```js
fontFamily: {
  // `display` is the UI chrome sans — used by 86+ call sites for bold
  // labels, tab buttons, sidebar items. Historically DM Sans; after the
  // Phase 5 font swap we keep Inter Tight here so chrome stays sans
  // and matches body without reintroducing a third font.
  display: ['"Inter Tight"', 'Inter', 'system-ui', 'sans-serif'],
  sans: ['"Inter Tight"', 'Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
  // `editorial` is the NEW utility — Fraunces serif for deliberate
  // hero headlines, big numerals, magazine-style moments. Not used
  // anywhere yet; opt in via `font-editorial` per surface.
  editorial: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
  mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
},
```

**Why Inter Tight instead of bringing DM Sans back:** Phase 5 already loaded Inter Tight in `index.html` and made it the body default. Reintroducing DM Sans would mean three font families on the page (Inter Tight body, DM Sans chrome, Fraunces editorial). Two is better than three, and Inter Tight bold reads cleanly as UI chrome.

**Step 3: Verify the change is syntactically valid**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (this doesn't exercise tailwind.config.js, but confirms no cross-file TS break).

Run: `cd frontend && npm run build 2>&1 | tail -20`
Expected: build succeeds, no Tailwind warnings about unknown classes. `font-display` continues to resolve (now to Inter Tight); `font-editorial` is a new class available for future use.

**Step 4: Visual smoke test — four pages**

Start the dev server if not running: `cd frontend && npm run dev`

Open each page and confirm:
1. **Home (`/`)** — sidebar labels, brand "DebugDuck", feed tabs, search placeholder all render in the same Inter Tight sans as the center column. No serif anywhere. No vertical scroll forced on default viewport (1440×900 assumed). User's original complaint disappears.
2. **App diagnostic (`/investigations/new?capability=troubleshoot_app`)** — `EvidenceFindings` headings read cleanly, no serif regressions.
3. **Database diagnostic** — `DatabaseWarRoom` chrome reads cleanly.
4. **Sessions list (`/investigations`)** — session cards don't ghost into serif.

If any page still shows a serif in chrome, grep for `font-editorial` to confirm no accidental usage snuck in.

**Step 5: Commit**

```bash
git add frontend/tailwind.config.js
git commit -m "$(cat <<'EOF'
fix(typography): revert font-display to sans, move Fraunces to font-editorial

Phase 5 commit 08e070ef reassigned the font-display Tailwind utility
from DM Sans to Fraunces serif. 86 existing call sites (sidebar, home
page, war rooms) silently flipped category, producing a broken serif-
chrome/sans-body mix the user reported as "no font is matching."

Fix: point font-display at Inter Tight so UI chrome stays sans and
matches the body font. Keep Fraunces available via a new
`font-editorial` utility for deliberate editorial moments — no call
sites use it yet.

Bonus side effect: the ~5-8% wider Fraunces glyph advance was pushing
home page right-rail panels into forced vertical scroll. Reverting
restores the intended layout.
EOF
)"
```

---

## Task 2: Replace hard-coded hex colors on HomePage feed tabs with tokens

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx:118-144`

**Step 1: Read the current tab block**

Lines 118-144 of `HomePage.tsx` contain two feed tab buttons ("Global Investigations" / "My Active") with inline `style={}` setting `color`, `borderBottom`, and `transition`. These bypass the `wr-*` token system.

**Step 2: Replace with token classes + a data attribute for active state**

Replace the block:
```tsx
<div className="flex items-center justify-between px-2 py-2 shrink-0">
  <div className="flex gap-5">
    <button
      onClick={() => setFeedTab('global')}
      className="text-sm font-display font-bold pb-1"
      style={{
        color: feedTab === 'global' ? 'white' : '#94a3b8',
        borderBottom: feedTab === 'global' ? '2px solid #e09f3e' : '2px solid transparent',
        transition: 'color 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
      }}
    >
      Global Investigations
    </button>
    <button
      onClick={() => setFeedTab('mine')}
      className="text-sm font-display font-bold pb-1"
      style={{
        color: feedTab === 'mine' ? 'white' : '#94a3b8',
        borderBottom: feedTab === 'mine' ? '2px solid #e09f3e' : '2px solid transparent',
        transition: 'color 200ms cubic-bezier(0.25, 1, 0.5, 1), border-color 200ms cubic-bezier(0.25, 1, 0.5, 1)',
      }}
    >
      My Active ({myActiveCount})
    </button>
  </div>
  <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
</div>
```

With:
```tsx
<div className="flex items-center justify-between px-2 py-2 shrink-0">
  <div className="flex gap-5">
    <button
      onClick={() => setFeedTab('global')}
      className={`text-sm font-display font-bold pb-1 border-b-2 transition-colors duration-200 ${
        feedTab === 'global'
          ? 'text-wr-text border-wr-accent'
          : 'text-wr-text-muted border-transparent hover:text-wr-text-secondary'
      }`}
    >
      Global Investigations
    </button>
    <button
      onClick={() => setFeedTab('mine')}
      className={`text-sm font-display font-bold pb-1 border-b-2 transition-colors duration-200 ${
        feedTab === 'mine'
          ? 'text-wr-text border-wr-accent'
          : 'text-wr-text-muted border-transparent hover:text-wr-text-secondary'
      }`}
    >
      My Active ({myActiveCount})
    </button>
  </div>
  <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
</div>
```

**Why `text-wr-text` / `text-wr-text-muted` / `border-wr-accent`:** these map through `:root` CSS variables defined in `index.css` and are the canonical tokens from Phase 3. `hover:text-wr-text-secondary` is an additive affordance (wasn't in the original — small refinement permissible because this is a tokens pass).

**Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

**Step 4: Visual verification**

Reload the home page. Click both tabs. Confirm:
1. Active tab text color matches the sidebar brand text color (both come from `--wr-text-primary`).
2. Inactive tab reads as muted (~`--wr-text-muted`).
3. Active tab has a 2px amber underline (`--wr-accent`).
4. Hover on inactive tab lightens the text slightly.
5. The 200ms transition still feels the same on click.

**Step 5: Commit**

```bash
git add frontend/src/components/Home/HomePage.tsx
git commit -m "$(cat <<'EOF'
refactor(home): feed tabs use wr-* tokens instead of hard-coded hex

Audit finding Medium #1 — feed tab buttons at HomePage.tsx:118-144
were using inline style={{ color: '#94a3b8', borderBottom: '2px solid
#e09f3e' }}. Move to text-wr-text / text-wr-text-muted / border-wr-accent
utilities so the tabs participate in the design token system and any
future theme-level color shifts flow through automatically.

Adds a subtle hover:text-wr-text-secondary affordance on inactive tabs.
EOF
)"
```

---

## Task 3: Final verification sweep

**Step 1: Grep for lingering hard-coded hex in the home page area**

Run: `rg -n "'#[0-9a-fA-F]{3,6}'" frontend/src/components/Home/`
Expected: a few remaining matches in other home components (e.g., `MetricStrip`, `EventTicker`, `CompactAgentFleet`). Document them in the task result but do NOT fix them — they're out of scope for this plan.

**Step 2: Confirm `font-editorial` is unused**

Run: `rg -n 'font-editorial' frontend/src`
Expected: zero matches. The utility is available but intentionally dormant.

**Step 3: Confirm Fraunces is still loaded (kept for future editorial use)**

Run: `rg -n 'Fraunces' frontend/index.html frontend/tailwind.config.js frontend/src/index.css`
Expected: 1 match in `index.html` (Google Fonts link) + 1 match in `tailwind.config.js` (the `editorial` stack). No other matches.

**Step 4: Smoke test the app diagnostic page one more time**

Because the audit's preservation contract (no pixel drift on app diagnostic page) still applies: open `/investigations/new?capability=troubleshoot_app` on a session you've used before. Confirm:
- `ForemanHUD` header reads cleanly (no serif)
- `EvidenceFindings` headings and cards render as they did pre-Phase-5
- `Investigator` and `Navigator` columns look unchanged

**No commit** — this is a verification gate.

---

## Task 4: Update plan document with outcome

**Files:**
- Modify: this plan file (`docs/plans/2026-04-11-home-page-audit-fix-plan.md`)

**Step 1: Append an "Outcome" section**

At the bottom of the file, add:
```markdown
---

## Outcome

- **Task 1 (font-display revert):** commit `<sha>` — home page + sidebar now render in Inter Tight. Vertical overflow resolved.
- **Task 2 (tab tokens):** commit `<sha>` — feed tabs participate in `wr-*` tokens.
- **Task 3 (verification):** passed / deferred items listed below.

### Deferred to follow-up work
- `SidebarNav` imperative hover handlers (audit Medium #2)
- Right-rail demotion + feed de-chroming (critique priorities 2 + 3)
- `MetricStrip` / `status-aurora` re-evaluation (critique priority 4)
- Font-editorial adoption on 1–3 editorial moments (critique suggestion)
```

**Step 2: Commit**

```bash
git add docs/plans/2026-04-11-home-page-audit-fix-plan.md
git commit -m "docs(plans): record home page audit fix outcome"
```

---

## Success Criteria

- `rg -c "'#[0-9a-fA-F]{6}'" frontend/src/components/Home/HomePage.tsx` returns 0.
- No serif glyphs visible anywhere in sidebar, home page chrome, or war room chrome.
- Home page renders without forced vertical scroll at 1440×900.
- App diagnostic page steady state remains pixel-stable (preservation contract from the parent plan).
- `npm run build` succeeds; `tsc --noEmit` is clean.
- `font-editorial` utility exists and is documented but unused.

## Rollback

If Task 1 causes any regression on a war room, a single `git revert <sha>` restores the *Phase 5 config state* — which is the broken serif-chrome state the user reported. Reverting is therefore not a real recovery path; it only exists as a kill switch if Inter Tight chrome produces a worse regression than serif chrome did. Note also that HEAD is not a strict revert to pre-Phase-5: pre-Phase-5 used DM Sans for chrome + Inter for body (two families, mixed categories), whereas HEAD uses Inter Tight for both. This is a deliberate third typographic state, chosen to avoid reintroducing a third font family. Task 2 is independent and safe to revert on its own.

---

## Outcome

- **Task 1 (font-display revert):** commits `eaddf3bc` + `325cb92b` — `font-display` now resolves to Inter Tight with a fallback chain byte-identical to `font-sans`. Home page, sidebar, and all 86 `font-display` call sites render in sans again. Vertical overflow on the home page resolved.
- **Task 2 (tab tokens):** commit `6d7f1bda` — `HomePage.tsx` feed tabs replaced inline `style={{ color: '#94a3b8', borderBottom: '2px solid #e09f3e' }}` with `text-wr-text` / `text-wr-text-muted` / `border-wr-accent` utilities and a `hover:text-wr-text-secondary` affordance.
- **Task 3 (verification):** passed. `font-editorial` confirmed unused, Fraunces still loaded in `index.html` for future editorial adoption, app diagnostic page steady state unchanged.
- **Typographic state note:** HEAD is "Inter Tight for all" — one family across chrome and body. This diverges from both the pre-Phase-5 state (DM Sans chrome + Inter body) and the Phase 5 state (Fraunces chrome + Inter Tight body). Chosen deliberately to avoid a three-font page.
- **Easing curve note:** Task 2 swapped the feed tabs' inline `cubic-bezier(0.25, 1, 0.5, 1)` (ease-out-quart) for Tailwind's `transition-colors duration-200`, which uses the Material standard `cubic-bezier(0.4, 0, 0.2, 1)`. The change is sub-threshold perceptually on a 200ms color transition but is technically different — recorded here for traceability.

### Deferred to follow-up work
- `SidebarNav` imperative hover handlers (audit Medium #2)
- Right-rail demotion + feed de-chroming (critique priorities 2 + 3)
- `MetricStrip` / `status-aurora` re-evaluation (critique priority 4)
- `font-editorial` adoption on 1–3 editorial moments (critique suggestion)
- **60-day checkpoint (≈2026-06-10) on `font-editorial` usage:** if still zero call sites, drop the utility from `tailwind.config.js` and remove the `Fraunces` family from the Google Fonts URL in `index.html` to reclaim the idle ~30KB.
- Out-of-scope hex leaks surfaced during Task 3 verification: `HowItWorks/investigationFlowData.ts`, `HowItWorks/ScenarioTab.tsx`, `HowItWorks/InvestigationFlowTab.tsx:162`, `HowItWorks/ArchitectureTab.tsx:10-17`, `EnvironmentHealth.tsx:31-34`.
