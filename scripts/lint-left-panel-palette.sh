#!/usr/bin/env bash
# Left-panel editorial palette linter.
#
# The Investigator column (War Room left panel) is moving to an editorial-
# dossier voice: warm-paper text on #1a1814 with red reserved strictly for
# Patient Zero. Cyan, amber-as-accent, and gradients are banned in this
# scope, regardless of how tempting they look in a PR.
#
# This script greps the Slot 2/3/4 component files for banned tokens and
# exits non-zero when it finds them. Wire into CI ahead of PR 2.
#
# Usage: bash scripts/lint-left-panel-palette.sh
#
# Scope — files governed by the editorial palette (expand as new files land
# in later PRs of the redesign):
#   - Investigator.tsx (top of column, owns Patient Zero)
#   - Verdict.tsx (Slot 2)          — PR 2
#   - StatusStrip.tsx (Slot 3)      — PR 2
#   - InvestigationLog.tsx (Slot 4) — PR 3
#
# Patient Zero itself (top ~100 lines of Investigator.tsx) uses red and is
# exempt. We don't try to scope by line number; instead the rules below
# target tokens Patient Zero does NOT use (cyan, specific amber accents).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Files under the editorial palette. Missing files are OK — they haven't
# been created yet in this PR sequence.
#
# Rollout note: Investigator.tsx is intentionally NOT in the initial scope
# because it contains ~19 pre-existing cyan (#07b6d5) usages in phase
# dividers + event nodes + reasoning stream. PR 3 rewrites those surfaces;
# that PR will add Investigator.tsx to TARGETS at the same time it removes
# the cyan. Scoping lint-to-new-files keeps PR 1's foundation green while
# still guarding the editorial components as they land.
TARGETS=(
  "frontend/src/components/Investigation/Investigator.tsx"         # PR 3 (cyan removed)
  "frontend/src/components/Investigation/Verdict.tsx"              # PR 2
  "frontend/src/components/Investigation/StatusStrip.tsx"          # PR 2
  "frontend/src/components/Investigation/PatientZeroMetadata.tsx"  # PR 2b
  "frontend/src/components/Investigation/InvestigationLog.tsx"     # PR 3
)

EXISTING=()
for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] && EXISTING+=("$f")
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "lint-left-panel-palette: no target files present yet; skipping."
  exit 0
fi

# Banned tokens below Patient Zero. Pattern is a regex passed to grep -E.
# Each entry is "pattern|explanation".
BANNED=(
  'wr-accent-2|cyan accent token — banned; use wr-paper / wr-text-muted'
  '#00f0ff|hex cyan — banned'
  '#07b6d5|hex cyan — banned'
  '#22d3ee|hex cyan — banned'
  'cyan-[0-9]|Tailwind cyan utility — banned'
  'shadow-glow|glow shadows — banned, use flat surfaces'
  'bg-gradient-to|gradient backgrounds — banned below Patient Zero'
  'from-danger-dim|dim-variant gradient — banned'
  'scanline|CRT scanline — banned; no sci-fi decoration'
)

# Scope carve-outs:
#  - Investigator.tsx legitimately renders the Patient Zero red gradient.
#    We allow gradient-related matches ONLY in that file. Other banned
#    tokens still apply.
#  - The "bg-gradient-to" pattern is exempted in Investigator.tsx; if
#    it leaks into other components, fail.

FOUND=0
for f in "${EXISTING[@]}"; do
  base="$(basename "$f")"
  for entry in "${BANNED[@]}"; do
    pat="${entry%%|*}"
    expl="${entry#*|}"

    # Gradient exemption for Patient Zero's host file
    if [[ "$base" == "Investigator.tsx" && "$pat" == "bg-gradient-to" ]]; then
      continue
    fi
    if [[ "$base" == "Investigator.tsx" && "$pat" == "from-danger-dim" ]]; then
      continue
    fi

    if grep -nE "$pat" "$f" >/tmp/lint-palette-hits 2>/dev/null; then
      if [[ -s /tmp/lint-palette-hits ]]; then
        echo "✗ $f — banned token \"$pat\" — $expl"
        cat /tmp/lint-palette-hits | sed 's/^/    /'
        FOUND=1
      fi
    fi
  done
done

rm -f /tmp/lint-palette-hits

if [[ $FOUND -eq 1 ]]; then
  echo
  echo "lint-left-panel-palette: FAIL — banned tokens found."
  echo "See docs/design/left-panel-editorial.md for the palette budget."
  exit 1
fi

echo "lint-left-panel-palette: OK"
exit 0
