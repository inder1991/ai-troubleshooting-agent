# Left-panel editorial voice — design principles

The War Room's left column (the `Investigator` panel, 3/12 grid span) is
moving from a "stacked dashboard of widgets" to an **editorial dossier** —
a single continuous document read top-to-bottom like a newspaper, not a
grid of cards scanned like a dashboard.

This doc is the palette + typography budget the redesign commits to. The
CI linter at `scripts/lint-left-panel-palette.sh` enforces the palette
half. The typography rules are stylistic; reviewers enforce them in PR.

## Layout anatomy (final state)

```
┌──────────────────────────────────────────────────────────┐
│  Slot 1 — Patient Zero (sticky red, unchanged skin)       │
│           + env context line (PR 2b)                       │
│           + service owner line (PR 2b)                     │
├──────────────────────────────────────────────────────────┤
│  Slot 2 — VERDICT (editorial prose, serif italic)         │
│           + blast-radius sentence (same voice)            │
├──────────────────────────────────────────────────────────┤
│  Slot 3 — Status Strip (single-line footnote marginalia)  │
├──────────────────────────────────────────────────────────┤
│  Slot 4 — Investigation Log (prose chronicle)             │
│           · phase dividers as small-caps, flush-left       │
│           · agent capsules as 2px left-border prose        │
│           · live breadcrumb inside active capsule          │
│           · reasoning chain behind disclosure              │
└──────────────────────────────────────────────────────────┘
```

## Palette budget (strict, scoped to `.warroom-left-editorial`)

| Token                              | Value     | Use                                                     |
| ---------------------------------- | --------- | ------------------------------------------------------- |
| `--wr-bg-primary`                  | `#1a1814` | panel background, only                                  |
| Red family (`#ef4444`, gradients)  | —         | **Patient Zero only** — banned everywhere else on left  |
| `--wr-paper` (NEW)                 | `#e8e0d4` | primary editorial text, Slot 2 VERDICT                  |
| `--wr-text-muted`                  | `#64748b` | metadata, timestamps, Status Strip, muted prose         |
| `--wr-text-subtle`                 | `#5a5148` | marginalia, reasoning disclosure glyph, *"gathering…"*  |
| Agent identity (`card-border-L/M/K/C/D`) | —   | 2px **left-borders** on log capsules only; no fills     |

### Banned below Patient Zero

The CI linter rejects any of these tokens in Slot 2/3/4 component files:

- Cyan in any form (`wr-accent-2`, `#00f0ff`, `#07b6d5`, `#22d3ee`, `cyan-*`)
- Amber used as accent chrome (kept only as global scrollbar token)
- Gradients (`bg-gradient-to`, `from-danger-dim`, etc.)
- Glow shadows (`shadow-glow-*`)
- CRT scanline overlays or other sci-fi decoration

### Exemption

`Investigator.tsx` itself (the host file) legitimately paints Patient
Zero's red gradient. Gradient patterns are ignored by the linter in that
file only; other banned tokens still fail.

## Typography

- **Body UI text** — `font-sans` (Inter Tight), 13–14px, `#e8e0d4`
- **Editorial hero** — `font-editorial` (Fraunces) italic, `clamp(17px, 1.2vw, 20px)`, `#e8e0d4` — used for VERDICT only
- **Editorial marginalia** — `font-editorial` italic, 12–14px, `#64748b`/`#e8e0d4 @ 0.75` — used for blast radius and Status Strip
- **Small caps** — `font-variant: small-caps` on a regular Inter Tight string, 11px letterspacing `0.15em`, `#64748b` — used for phase dividers in Slot 4
- **Mono** — `font-mono` (JetBrains Mono), 11px, `#64748b` — used for metadata, env context (cluster / version / namespace), stack traces, tool-call args; nowhere else
- **Tabular nums** — on timers, token counts, elapsed times

Vertical rhythm is managed by `@capsizecss/core` + `@capsizecss/metrics`
to trim invisible font padding so `margin-*` values render as measured.

## Interaction

- **No modals, no toasts** for left-panel content — progressive disclosure via inline accordion only.
- **Radix UI** `react-accordion` for all mutually-exclusive expansions (Status Strip clauses, reasoning disclosure).
- **React Spring** for height animations (physics-based, interruptible; respects `prefers-reduced-motion: reduce`).
- **Lenis** for smooth-scroll coordination with the middle column (Status Strip → DisagreementStrip scroll-to).
- **TanStack Virtual** for the Slot 4 log body — only visible rows render.

## Absence is a signal

Any data field that is missing causes the corresponding line to **not
render at all**. No "no divergences found" placeholders, no "owner
unknown" greyed-out text. Empty ≠ zero.

## Rollout

See the full PR plan in `docs/design/left-panel-editorial.plan.md`
(tracked separately). Six PRs total, ~1,410 LOC, executed top-down from
foundation → slots → cleanup → right-panel AGENTS promotion.

## CI enforcement

- `scripts/lint-left-panel-palette.sh` — palette linter, runs on every PR that touches the scope. Exits non-zero on banned tokens.
- Component unit tests — assert absence of card classes (`rounded-*`, `border-[^l]`, `bg-wr-severity-*`) in Slot 2/3 DOM.
- Playwright perf — 60fps scroll with 2000 log entries (added in PR 3).

## Deliberate departures from AI-product vocabulary

This redesign intentionally rejects patterns common in AI observability
products: cyan-on-dark palettes, glowing metric cards, CRT scanlines,
hero-metric cards with big confidence percentages, all-caps mono labels,
row-of-pill status strips. Those are the fingerprints of AI-generated
dashboards. The editorial voice is the differentiator — and the
linter + design doc exist to keep future changes from quietly drifting
back toward the cliché.
