/**
 * Platform design tokens — single source of truth for all raw color values
 * used in the Workflow Builder / Workflow Runs UI.
 *
 * Usage:  import { t } from '../../../styles/tokens';
 *         style={{ background: t.bgSurface, borderColor: t.borderDefault }}
 */
export const t = {
  // ── Backgrounds ────────────────────────────────────────────────────────
  bgBase:    '#0a1214',   // outermost view backgrounds
  bgSurface: '#0c1a1f',   // panel / detail pane surfaces
  bgDeep:    '#080f12',   // inputs, deepest insets
  bgTrack:   '#1a2428',   // progress-bar tracks, subtle dividers

  // ── Borders ────────────────────────────────────────────────────────────
  borderDefault: '#1e2a2e',  // standard dividers / panel borders
  borderSubtle:  '#1a2428',  // intra-panel dividers
  borderFaint:   '#0f1a1e',  // row separators inside panels

  // ── Text ───────────────────────────────────────────────────────────────
  textPrimary:   '#e8e0d4',  // headings, primary labels
  textSecondary: '#9a9080',  // supporting body copy
  textMuted:     '#64748b',  // secondary metadata
  textFaint:     '#3d4a50',  // labels, section headers, placeholders

  // ── Accent (cyan) ──────────────────────────────────────────────────────
  cyan:         '#07b6d5',
  cyanBg:       'rgba(7,182,213,0.08)',
  cyanBorder:   'rgba(7,182,213,0.3)',
  cyanHover:    'rgba(7,182,213,0.04)',
  cyanSelected: 'rgba(7,182,213,0.06)',

  // ── Status — success ───────────────────────────────────────────────────
  green:       '#22c55e',
  greenBg:     'rgba(34,197,94,0.1)',
  greenBorder: 'rgba(34,197,94,0.4)',

  // ── Status — warning ───────────────────────────────────────────────────
  amber:       '#f59e0b',
  amberBg:     'rgba(245,158,11,0.06)',
  amberBorder: 'rgba(245,158,11,0.3)',

  // ── Status — error / danger ────────────────────────────────────────────
  red:       '#ef4444',
  redBg:     'rgba(239,68,68,0.08)',
  redBorder: 'rgba(239,68,68,0.3)',

  // ── On-accent text ─────────────────────────────────────────────────────
  textOnAccent: '#ffffff',  // white text on solid cyan/accent backgrounds

  // ── Shadows ────────────────────────────────────────────────────────────
  shadowModal: '0 24px 48px rgba(0,0,0,0.5)',
} as const;
