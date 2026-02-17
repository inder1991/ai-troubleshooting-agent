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
        'duck-bg': '#0f2023',
        'duck-card': '#1e2f33',
        'duck-border': '#224349',
        'duck-accent': '#07b6d5',
        'duck-surface': '#162a2e',
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
    },
  },
  plugins: [],
}
