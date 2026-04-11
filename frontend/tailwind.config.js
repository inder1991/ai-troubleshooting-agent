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
          border: 'var(--wr-border)',
          'border-subtle': 'var(--wr-border-subtle)',
          accent: 'var(--wr-accent)',
        },
        duck: {
          bg:      '#1a1814',
          card:    '#252118',
          border:  '#3d3528',
          accent:  '#e09f3e',
          surface: '#1e1b15',
          panel:   '#161310',    // warmed — was #12110e (too cold)
          sidebar: '#13110d',    // warmed — was #0d0c0a (dead black)
          flyout:  '#13110d',    // matches sidebar — was #0f0e0b
          muted:   '#8a7e6b',
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
        display: ['"DM Sans"', 'Inter', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
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
