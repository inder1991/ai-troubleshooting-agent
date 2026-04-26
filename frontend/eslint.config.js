// Q14 — WCAG 2.2 AA gate via jsx-a11y at error level (Sprint H.0b.7).
// Q18 — full import-rule wiring (import/order, no-default-export, alias
//       enforcement, react-hooks, typescript-eslint) lands in Sprint H.0b.11.
//
// This is a minimal flat-config stub: it loads jsx-a11y/recommended at
// error level so any project consuming the harness today gets a11y
// linting. The rest of the plugin set is wired in H.0b.11 once the
// underlying packages (@eslint/js, typescript-eslint, eslint-plugin-react-hooks,
// eslint-plugin-react-refresh) are installed.

import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  { ignores: ["dist", "node_modules", "e2e", "coverage"] },
  {
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    plugins: {
      "jsx-a11y": jsxA11y,
    },
    rules: {
      // Q14: jsx-a11y recommended rules at error level.
      ...jsxA11y.configs.recommended.rules,
    },
  },
];
