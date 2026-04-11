/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        'primary': '#e09f3e',
        'background-light': '#f5f0e8',
        'background-dark': '#1a1814',
        'neutral-slate': '#252118',
        'neutral-border': '#3d3528',
        wr: {
          bg: 'var(--wr-bg-primary)',
          surface: 'var(--wr-bg-surface)',
          inset: 'var(--wr-bg-inset)',
          elevated: 'var(--wr-bg-elevated)',
          border: 'var(--wr-border)',
          'border-subtle': 'var(--wr-border-subtle)',
          'border-strong': 'var(--wr-border-strong)',
          text: 'var(--wr-text-primary)',
          'text-secondary': 'var(--wr-text-secondary)',
          'text-muted': 'var(--wr-text-muted)',
          'text-subtle': 'var(--wr-text-subtle)',
          accent: 'var(--wr-accent)',
          'accent-glow': 'var(--wr-accent-glow)',
          'accent-2': 'var(--wr-accent-2)',
          'accent-2-glow': 'var(--wr-accent-2-glow)',
          'severity-high': 'var(--wr-severity-high)',
          'severity-medium': 'var(--wr-severity-medium)',
          'severity-low': 'var(--wr-severity-low)',
          'status-success': 'var(--wr-status-success)',
          'status-warning': 'var(--wr-status-warning)',
          'status-error': 'var(--wr-status-error)',
          'status-pending': 'var(--wr-status-pending)',
        },
        // Legacy duck-* tokens now alias to wr-* (transparent to consumers)
        duck: {
          bg:      'var(--wr-bg-primary)',
          card:    'var(--wr-bg-elevated)',
          border:  'var(--wr-border-strong)',
          accent:  'var(--wr-accent)',
          surface: 'var(--wr-bg-elevated)',
          panel:   'var(--wr-bg-inset)',
          sidebar: 'var(--wr-bg-inset)',
          flyout:  'var(--wr-bg-inset)',
          muted:   'var(--wr-text-muted)',
        },
      },
      fontSize: {
        // Legacy (keep for one migration cycle, then delete in Phase 6)
        micro: ['10px', { lineHeight: '14px', letterSpacing: '0.05em' }],
        nano:  ['8px',  { lineHeight: '12px', letterSpacing: '0.05em' }],
        // Canonical scale — everything below 12px is chrome-only, never body text
        'chrome':     ['11px', { lineHeight: '14px', letterSpacing: '0.02em' }],
        'body-xs':    ['12px', { lineHeight: '16px' }],
        'body-sm':    ['13px', { lineHeight: '18px' }],
        'body':       ['14px', { lineHeight: '20px' }],
        'body-lg':    ['15px', { lineHeight: '22px' }],
        'heading-xs': ['16px', { lineHeight: '22px', letterSpacing: '-0.01em', fontWeight: '600' }],
        'heading-sm': ['18px', { lineHeight: '24px', letterSpacing: '-0.01em', fontWeight: '600' }],
        'heading':    ['22px', { lineHeight: '28px', letterSpacing: '-0.015em', fontWeight: '600' }],
        'heading-lg': ['28px', { lineHeight: '34px', letterSpacing: '-0.02em',  fontWeight: '700' }],
        'display-sm': ['36px', { lineHeight: '42px', letterSpacing: '-0.025em', fontWeight: '700' }],
        'display':    ['48px', { lineHeight: '54px', letterSpacing: '-0.03em',  fontWeight: '700' }],
        'display-lg': ['64px', { lineHeight: '68px', letterSpacing: '-0.035em', fontWeight: '700' }],
      },
      fontFamily: {
        // `display` is the UI chrome sans — used by 86+ call sites for bold
        // labels, tab buttons, sidebar items. Historically DM Sans; after the
        // Phase 5 font swap we keep Inter Tight here so chrome stays sans
        // and matches body without reintroducing a third font.
        display: ['"Inter Tight"', 'Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
        sans: ['"Inter Tight"', 'Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
        // `editorial` is the NEW utility — Fraunces serif for deliberate
        // hero headlines, big numerals, magazine-style moments. Not used
        // anywhere yet; opt in via `font-editorial` per surface.
        editorial: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        lg: '0.5rem',
        xl: '0.75rem',
        full: '9999px',
      },
      animation: {
        'pulse-amber': 'pulse-amber 2s infinite',
      },
      keyframes: {
        'pulse-amber': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(245, 158, 11, 0.4)' },
          '50%': { boxShadow: '0 0 15px 5px rgba(245, 158, 11, 0.6)' },
        },
      },
    },
  },
  plugins: [],
}
