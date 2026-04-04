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
        micro: ['10px', { lineHeight: '14px', letterSpacing: '0.05em' }],
        nano:  ['8px',  { lineHeight: '12px', letterSpacing: '0.05em' }],
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
