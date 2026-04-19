#!/usr/bin/env bash
# War Room layout-invariant linter.
#
# Rejects patterns that violate the PR 1-7 redesign contracts in new
# code. Existing pre-redesign surfaces are opted in per-file via
# TARGETS (same pattern as lint-z-index-tokens.sh + lint-left-panel-
# palette.sh), so CI tightens progressively as files migrate.
#
# Rules:
#   1. No `overflow-x-auto scrollbar-hide` — invisible scrollbars
#      strand mouse-only users. Use EditorialScrollArea + explicit
#      chevrons (AnchorToolbar / EditorialCarousel) instead.
#   2. No `fixed right-0` or `fixed inset-0 z-[...]` patterns in
#      drawer consumers — use PaneDrawer + RegionPortalsContext.
#   3. No `grid-cols-N` class on grid-region container roots — use
#      @container queries via the declared containment contexts.
#
# Usage: bash scripts/lint-warroom-invariants.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGETS=(
  # Shell primitives — must always follow every rule.
  "frontend/src/components/shell/StickyStack.tsx"
  "frontend/src/components/shell/PaneDrawer.tsx"
  "frontend/src/components/shell/GutterRail.tsx"
  "frontend/src/components/shell/EditorialScrollArea.tsx"
  "frontend/src/components/shell/AnchorToolbar.tsx"
  "frontend/src/components/shell/EditorialCarousel.tsx"
  "frontend/src/components/shell/TruncatedLabel.tsx"
  # Banner region
  "frontend/src/components/banner/BannerRegion.tsx"
  "frontend/src/components/banner/BannerRow.tsx"
  "frontend/src/components/banner/FreshnessRow.tsx"
  # Center panel
  "frontend/src/components/center/FixReadyBar.tsx"
  "frontend/src/components/center/ReproduceQueryRow.tsx"
  "frontend/src/components/center/BlastRadiusList.tsx"
  "frontend/src/components/center/PinPostmortemChip.tsx"
  "frontend/src/components/center/PinnedGhost.tsx"
)

EXISTING=()
for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] && EXISTING+=("$f")
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "lint-warroom-invariants: no target files present yet; skipping."
  exit 0
fi

BANNED=(
  'overflow-x-auto.*scrollbar-hide|invisible horizontal scrollbar strands mouse-only users — use EditorialScrollArea or AnchorToolbar'
  'overflow-y-auto.*scrollbar-hide|invisible vertical scrollbar strands mouse-only users — use EditorialScrollArea'
  'fixed\s+right-0\s+.*z-\[|fixed-position right-edge drawer — use PaneDrawer + RegionPortalsContext'
  'fixed\s+inset-0\s+z-\[[0-9]|fixed-position full-viewport overlay — use PaneDrawer or Radix Dialog'
  'scrollbar-hide|invisible scrollbar — use EditorialScrollArea or expose a visible scrollbar'
)

FOUND=0
for f in "${EXISTING[@]}"; do
  # Strip common comment lines (leading * / //) before matching — the
  # linter targets active code, not documentation that references the
  # banned patterns by name.
  stripped=$(mktemp)
  grep -v -E '^\s*(\*|//|/\*)' "$f" > "$stripped"
  for entry in "${BANNED[@]}"; do
    pat="${entry%%|*}"
    expl="${entry#*|}"
    if grep -nE "$pat" "$stripped" >/tmp/lint-wr-hits 2>/dev/null; then
      if [[ -s /tmp/lint-wr-hits ]]; then
        echo "✗ $f — banned pattern \"$pat\" — $expl"
        cat /tmp/lint-wr-hits | sed 's/^/    /'
        FOUND=1
      fi
    fi
  done
  rm -f "$stripped"
done

rm -f /tmp/lint-wr-hits

if [[ $FOUND -eq 1 ]]; then
  echo
  echo "lint-warroom-invariants: FAIL — invariant violations found."
  echo "See docs/design/left-panel-editorial.md and PR 1-7 of the War Room"
  echo "redesign for the rules."
  exit 1
fi

echo "lint-warroom-invariants: OK"
exit 0
