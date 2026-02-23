/** Shared design tokens for consistent styling across the War Room UI. */

export const tokens = {
  /** Card container styles */
  card: 'bg-slate-900/40 border border-slate-800 rounded-xl',

  /** Badge styles — text-[9px] font-bold px-1.5 py-0.5 rounded border */
  badge: 'text-[9px] font-bold px-1.5 py-0.5 rounded border',

  /** Padding scales */
  padding: {
    tight: 'px-2 py-1',
    default: 'px-3 py-1.5',
    loose: 'px-4 py-2',
  },

  /** Status color maps (background + border + text) */
  status: {
    error: 'bg-red-500/10 border-red-500/20 text-red-400',
    warning: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
    success: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    info: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-400',
  },

  /** Disabled button styling */
  disabled: 'disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0',

  /** Focus-visible ring */
  focusRing: 'focus-visible:ring-2 focus-visible:ring-[#07b6d5]/50 focus-visible:outline-none',

  /** Transition defaults */
  transition: 'transition-colors duration-150',

  /** Hover effect for clickable cards */
  hoverCard: 'hover:bg-slate-800/40 transition-colors duration-150 cursor-pointer',
} as const;
