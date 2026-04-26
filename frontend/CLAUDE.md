---
scope: frontend/
owner: "@platform-team"
priority: high
type: directory
---

# Frontend conventions

These rules apply to all code under `frontend/`. They override the root
`CLAUDE.md` on conflict.

## Stack
- React + TypeScript + Vite. Tailwind for styling.
- TanStack Query for server state. React Context / `useState` for UI state.
- shadcn/ui-style primitives in `components/ui/` (Radix under the hood).
- React Router v6 with `createBrowserRouter` (single table in `src/router.tsx`).
- Vitest for unit/integration. Playwright for e2e (in `frontend/e2e/`).

## Styling (Q1)
- Tailwind utility classes only.
- Inline `style={{...}}` allowed ONLY for dynamic values (width %, transform, etc.).
- No CSS/SCSS imports. No `styled-components`. No `@emotion`.
- Class merging via `cn()` from `@/lib/utils`.
- Token namespace is `wr-*`. `duck-*` is legacy and BANNED in new code.

## State (Q2) + data fetching (Q3)
- Server state: TanStack Query.
- UI state: local `useState` or React Context.
- Global UI state: scoped Zustand stores in `frontend/src/stores/` with
  `// JUSTIFICATION: <why this needs to be global>` leading comment.
- Components do NOT call `fetch` / `axios` directly. They consume hooks.
- All HTTP goes through `services/api/client.ts` → typed domain functions
  in `services/api/<domain>.ts` → hook wrappers in `hooks/use<X>.ts`.
- Redux / MobX / Recoil / Jotai BANNED. Axios BANNED.

## Primitives (Q4)
- All reusable UI primitives live in `components/ui/` (shadcn pattern).
- Feature components compose primitives; never use raw `<button>`,
  `<input>`, `<select>`, `<a onClick>` in feature code.
- MUI / Chakra / Mantine BANNED.

## Routing (Q6)
- All routes declared in `frontend/src/router.tsx`. No nested `<Routes>` blocks.
- Page components lazy-imported via `React.lazy(() => import('./pages/X'))`.
- Internal nav: `<Link to="...">` or `useNavigate()`. Raw `<a href="/...">`
  is BANNED for internal nav.

## Tests (Q5)
- Vitest tests colocated as `*.test.ts(x)`.
- Playwright e2e specs live ONLY under `frontend/e2e/`.
- Coverage gate: `services/api/ ≥ 90%`, `hooks/ ≥ 85%` (vitest threshold config).
- Jest / Cypress BANNED.

## Accessibility (Q14)
- Target: WCAG 2.2 AA.
- Every primitive in `components/ui/` ships with an axe-clean Vitest test.
- Incident-critical pages have axe-clean Playwright e2e specs.
- jsx-a11y eslint plugin at error level — no overrides without
  `// a11y-justified:` comment.

## Imports & naming (Q18)
- Use path alias `@/` (mapped to `frontend/src/`). No `../../../` paths.
- Named exports only. Default exports allowed only in `pages/` and
  config files (`vite.config.ts`, etc.).
- File naming: `Component.tsx` (PascalCase), `useThing.ts` (camelCase
  starting with `use`), `kebab-case/` directories.
