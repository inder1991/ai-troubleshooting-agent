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
        'primary': '#07b6d5',
        'background-light': '#f5f8f8',
        'background-dark': '#0f2023',
        'neutral-slate': '#1e2f33',
        'neutral-border': '#224349',
        duck: {
          bg:      '#0f2023',
          card:    '#1e2f33',
          border:  '#224349',
          accent:  '#07b6d5',
          surface: '#162a2e',
          panel:   '#0a1517',
          sidebar: '#000000',
          flyout:  '#090909',
          muted:   '#94a3b8',
        },
      },
      fontSize: {
        micro: ['10px', { lineHeight: '14px', letterSpacing: '0.05em' }],
        nano:  ['8px',  { lineHeight: '12px', letterSpacing: '0.05em' }],
      },
      fontFamily: {
        display: ['Inter', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
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
