# War Room redesign — reference

Living index for the seven-PR War Room redesign that shipped between
#55 and #61. Each PR is self-contained with acceptance criteria,
test coverage, and linter enforcement; taken together they move the
Investigation page from a flex-inside-flex-plus-fixed-overlays
layout to a named-region CSS grid with reserved gutter, pane-portaled
drawers, editorial banner + scroll primitives, four outcome-driving
centre-panel additions, shared pin state, and CI-enforced invariants.

## PR map

| PR | Scope | LOC | Visible change? |
|---|---|---|---|
| **#55** | Grid shell foundation — named regions, reserved gutter, z-index tokens, cascade layers, StickyStack / PaneDrawer / GutterRail primitives, IncidentLifecycleContext | ~1,670 | No (dormant) |
| **#56** | Banner + freshness region — signal scheduler, Commander's Intent voice, editorial micro-typography, manual-override scaffold | ~1,350 | Yes |
| **#57** | Drawer refactor — ChatDrawer / TelescopeDrawerV2 / SurgicalTelescope / LedgerTriggerTab portal into their owning column regions | ~440 | Yes |
| **#58** | Scroll + sticky + anchor discipline — EditorialScrollArea, AnchorToolbar with chevrons + fade-mask, section-anchor scroll-margin via `--sticky-stack-h` | ~440 | Yes |
| **#59** | Four centre-panel additions — FixReadyBar, ReproduceQueryRow, BlastRadiusList, PinPostmortemChip | ~1,440 | Yes |
| **#60** | Carousel + pin ghost + truncated label — EditorialCarousel, TruncatedLabel, Zustand pinStore, PinnedGhost inline placeholder | ~770 | Yes (root-cause demo) |
| **#61** | Test + CI hardening — Playwright multi-viewport, axe-core a11y, layout invariants lint, CI wire-up | ~550 | No |

**Total:** ~6,660 LOC across 7 PRs. Deep frontend test bench
expansion: 24 → 629 tests (pre-redesign) + multi-viewport Playwright
+ axe-core.

## Invariants enforced at build time

Three shell scripts run on every PR via `.github/workflows/ci.yml`:

1. **`scripts/lint-left-panel-palette.sh`** — editorial palette scope.
   No cyan, no amber-as-accent, no gradient, no glow in the files
   listed under the editorial scope (left-panel primitives + banner).
2. **`scripts/lint-z-index-tokens.sh`** — rejects raw z-index literals
   in shell + editorial + centre component files; only
   `var(--z-*)` references pass.
3. **`scripts/lint-warroom-invariants.sh`** — rejects
   `overflow-x-auto scrollbar-hide`, `fixed right-0 z-[…]`, and
   other reachability-breaking patterns in the primitives.

## Playwright coverage (PR 7)

`playwright.config.ts` declares five viewport projects —
1024 / 1280 / 1440 / 1920 / 2560 — each running
`warroom.layout.spec.ts`, `warroom.a11y.spec.ts`, and
`warroom.overlap.spec.ts`. Together they enforce:

- Visual regression at every viewport
- No axe-core serious / critical violations
- ChatDrawer open never hides investigator / evidence columns
- Jump-links always land below the sticky stack
- LedgerTriggerTab lives inside the gutter column
- Anchor-toolbar chevrons are reachable by accessible role

## Follow-ups (tracked, not shipped)

- Full ghost swap on remaining 7 VineCards (cascading, ungrouped,
  findings, metrics, k8s, blast-radius, service-flow, causality,
  code-nav, correlated). Pattern is proven on root-cause; rollout is
  mechanical.
- Container-query lint rule — reject `grid-cols-N` on column roots.
  Design noted; not yet implemented.
- Backend enrichments that would upgrade centre-panel surfaces:
  `patient_zero.owning_team`, cluster + version on PatientZero,
  explicit revenue impact on BlastRadius.

## How to evolve safely

- Add a new surface → register it in the linter `TARGETS` arrays.
- Touch the grid shell → run `bash scripts/lint-warroom-invariants.sh`
  locally before pushing.
- Touch a palette token → the palette-lint + CI diff tell you
  what downstream is affected.
- Add a sticky element in a column → wrap it in `<StickyStack>`; the
  `--sticky-stack-h` var auto-adjusts, and every
  `[data-scroll-anchor]` lands correctly.
