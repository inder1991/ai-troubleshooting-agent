#!/usr/bin/env bash
# Z-index token linter.
#
# The War Room uses a strict token scale (see --z-* custom properties
# in frontend/src/index.css). Any raw z-index number — either Tailwind
# `z-[<N>]` arbitrary values or inline `zIndex: <N>` / `z-index: <N>`
# — bypasses the scale and creates the class of stacking bugs the PR-1
# shell rebuild was meant to eliminate permanently.
#
# This linter rejects raw z-index values in the editorial + shell
# component scope. Token references (e.g. `z-[var(--z-drawer)]` or
# `style={{ zIndex: 'var(--z-column-sticky)' }}`) pass.
#
# Scope grows over time — each PR that lands a new component adds
# that component's path to TARGETS. This way, the linter guards new
# code from day one while existing code gets migrated opportunistically.
#
# Usage: bash scripts/lint-z-index-tokens.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Files under z-index discipline. Additions from each PR land here.
TARGETS=(
  "frontend/src/components/shell/StickyStack.tsx"
  "frontend/src/components/shell/PaneDrawer.tsx"
  "frontend/src/components/shell/GutterRail.tsx"
  "frontend/src/contexts/IncidentLifecycleContext.tsx"
  # PR 2 — banner region components
  "frontend/src/components/banner/BannerRegion.tsx"
  "frontend/src/components/banner/BannerRow.tsx"
  "frontend/src/components/banner/FreshnessRow.tsx"
  "frontend/src/components/banner/signalScheduler.ts"
  "frontend/src/components/banner/phaseNarrative.ts"
  "frontend/src/contexts/AppControlContext.tsx"
  # PR 3 — drawer portal consumers
  "frontend/src/contexts/RegionPortalsContext.tsx"
  "frontend/src/components/Chat/ChatDrawer.tsx"
  "frontend/src/components/Chat/LedgerTriggerTab.tsx"
  "frontend/src/components/Investigation/TelescopeDrawerV2.tsx"
  "frontend/src/components/Investigation/SurgicalTelescope.tsx"
  # PR 4 — scroll + anchor primitives
  "frontend/src/components/shell/EditorialScrollArea.tsx"
  "frontend/src/components/shell/AnchorToolbar.tsx"
)

EXISTING=()
for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] && EXISTING+=("$f")
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "lint-z-index-tokens: no target files present yet; skipping."
  exit 0
fi

# Regex patterns that indicate a raw z-index value. Each entry is
# "pattern|explanation". We allow:
#   · z-[var(--z-...)]
#   · z-index: var(--z-...)
#   · zIndex: 'var(--z-...)'
# We reject:
#   · z-[0-9]+ without a var() reference
#   · z-index: <literal number>
#   · zIndex: <literal number>
BANNED=(
  'z-\[[0-9]+\]|Tailwind arbitrary z-index literal — use z-[var(--z-*)]'
  'z-index:\s*[0-9]+|raw CSS z-index literal — use var(--z-*)'
  'zIndex:\s*[0-9]+|inline numeric zIndex — use var(--z-*) string'
)

FOUND=0
for f in "${EXISTING[@]}"; do
  for entry in "${BANNED[@]}"; do
    pat="${entry%%|*}"
    expl="${entry#*|}"

    # grep for the banned pattern. -E for extended regex.
    if grep -nE "$pat" "$f" >/tmp/lint-z-hits 2>/dev/null; then
      if [[ -s /tmp/lint-z-hits ]]; then
        echo "✗ $f — banned z-index pattern — $expl"
        cat /tmp/lint-z-hits | sed 's/^/    /'
        FOUND=1
      fi
    fi
  done
done

rm -f /tmp/lint-z-hits

if [[ $FOUND -eq 1 ]]; then
  echo
  echo "lint-z-index-tokens: FAIL — raw z-index values found."
  echo "See frontend/src/index.css for the --z-* scale."
  exit 1
fi

echo "lint-z-index-tokens: OK"
exit 0
