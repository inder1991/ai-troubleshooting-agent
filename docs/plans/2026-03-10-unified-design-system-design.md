# Unified Design System & Performance Upgrade

**Date:** 2026-03-10
**Status:** Approved
**Scope:** Frontend design token sweep, TanStack Query migration, accessibility hardening

## Problem Statement

The dashboard suffers from visual inconsistencies caused by mixed usage of arbitrary hex codes and standard Tailwind classes. 26 inline `style={{}}` blocks, 23 hardcoded hex values, and 13 redundant `fontFamily` declarations fragment the design system. Data fetching uses raw `useEffect`/`setInterval` anti-patterns, and accessibility fundamentals (focus rings, aria labels, screen reader hygiene) are missing.

## Audit Results

| File | Inline styles | fontFamily | Hardcoded hex |
|------|--------------|------------|---------------|
| HomePage.tsx | 10 | 3 | 8 |
| CapabilityLauncher.tsx | 6 | 2 | 3 |
| QuickActionsPanel.tsx | 2 | 2 | 7 |
| LiveIntelligenceFeed.tsx | 1 | 1 | 3 |
| MetricRibbon.tsx | 0 | 0 | 0 |
| SidebarNav.tsx | 7 | 5 | 2+ |
| **Total** | **26** | **13** | **23+** |

## Approach

**Component-by-component sweep** (Approach A): Prerequisite tasks first (Tailwind config, Badge, TanStack install), then sweep each component file individually. Each commit is atomic and testable.

---

## Phase 1: Design Token Sweep

### 1.1 Tailwind Config

Replace `frontend/tailwind.config.js` entirely:

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
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
        }
      },
      fontSize: {
        micro: ['10px', { lineHeight: '14px', letterSpacing: '0.05em' }],
        nano:  ['8px',  { lineHeight: '12px', letterSpacing: '0.05em' }],
      },
      animation: {
        'pulse-amber': 'pulse-amber 2s infinite',
      },
      keyframes: {
        'pulse-amber': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(245, 158, 11, 0.4)' },
          '50%': { boxShadow: '0 0 15px 5px rgba(245, 158, 11, 0.6)' },
        }
      }
    },
  },
  plugins: [],
}
```

### 1.2 Badge Component

Create `frontend/src/components/ui/Badge.tsx`:

```tsx
import React from 'react';

export type BadgeType = 'NEW' | 'PREVIEW' | 'BETA';

interface BadgeProps {
  type: BadgeType;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ type, className = '' }) => {
  const styleMap: Record<BadgeType, string> = {
    NEW: 'bg-duck-accent/15 text-duck-accent border-duck-accent/30',
    PREVIEW: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    BETA: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  };

  return (
    <span
      className={`
        inline-flex items-center justify-center
        px-1.5 py-0.5 rounded border
        text-nano font-black uppercase tracking-widest
        ${styleMap[type]}
        ${className}
      `}
    >
      {type}
    </span>
  );
};
```

### 1.3 Token Mapping Reference

| Old (hardcoded) | New (semantic) |
|-----------------|----------------|
| `#0f2023` / `bg-[#0f2023]` | `bg-duck-bg` |
| `#0a1517` / `bg-[#0a1517]` | `bg-duck-panel` |
| `#224349` / `border-[#224349]` | `border-duck-border` |
| `#07b6d5` / `text-[#07b6d5]` | `text-duck-accent` |
| `#94a3b8` / `text-[#94a3b8]` | `text-duck-muted` |
| `cyan-400` / `cyan-500` (in Home/Layout) | `duck-accent` |
| `rgba(15,32,35,0.5)` inline | `bg-duck-panel/50` |
| `backdropFilter: 'blur(12px)'` inline | `backdrop-blur-md` |
| `text-[8px]` | `text-nano` |
| `text-[10px]` | `text-micro` |

### 1.4 fontFamily Removal

All 13 `style={{ fontFamily: 'Material Symbols Outlined' }}` declarations are redundant (the CSS class `.material-symbols-outlined` in `index.css` handles this globally). Remove them all. Keep only `style={{ fontSize: N }}` where icon sizing differs from default.

### 1.5 Transition Standardization

All interactive elements (buttons, sidebar links, cards) should use:
```
transition-all duration-200 ease-in-out
```

---

## Phase 2: TanStack Query Migration

### 2.1 Install & Provider

```bash
npm install @tanstack/react-query
```

Wrap App in `QueryClientProvider`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AppInner />
      </ToastProvider>
    </QueryClientProvider>
  );
}
```

### 2.2 LiveIntelligenceFeed Migration

Replace `useEffect`/`setInterval` with:

```tsx
const { data: sessions = [], isLoading, isError } = useQuery({
  queryKey: ['live-sessions'],
  queryFn: listSessionsV4,
  refetchInterval: 10000,
  staleTime: 5000,
});
```

Add discrete UI states for loading, error, and empty.

### 2.3 MetricRibbon Migration

Use same query key `['live-sessions']` — React Query deduplicates. Remove `sessions` prop. Extract `todayStr` outside the filtering function.

```tsx
const todayStr = new Date().toDateString();
const isResolvedToday = (s: V4Session) => {
  if (!['complete', 'diagnosis_complete'].includes(s.status)) return false;
  return new Date(s.updated_at).toDateString() === todayStr;
};
```

### 2.4 HomePage Prop Cleanup

Remove `sessions` and `onSessionsChange` from `HomePageProps`. Children self-fetch from query cache.

---

## Phase 3: Accessibility

### 3.1 Screen Reader Hygiene

- Add `aria-hidden="true"` to all 13+ `material-symbols-outlined` spans
- Add `aria-label` to all icon-only buttons (notifications, profile, new mission, nav items)

### 3.2 Keyboard Navigation

Add to all interactive elements:
```
focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent
```

### 3.3 Font Preloading

Add to `index.html` `<head>` before the stylesheet:

```html
<link
  rel="preload"
  href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0"
  as="style"
/>
```

---

## Component Sweep Matrix

Each component gets all 3 phases in a single atomic commit:

| # | Component | Phase 1 (Tokens) | Phase 2 (Query) | Phase 3 (a11y) |
|---|-----------|-------------------|-----------------|----------------|
| 1 | tailwind.config.js | Full rewrite | - | - |
| 2 | Badge.tsx | Create | - | - |
| 3 | App.tsx | - | QueryClientProvider | - |
| 4 | index.html | - | - | Font preload |
| 5 | HomePage.tsx | 10 inline→0, 8 hex→tokens | Remove prop drilling | aria-labels, focus rings |
| 6 | CapabilityLauncher.tsx | 6 inline→0, Badge | - | aria-hidden |
| 7 | QuickActionsPanel.tsx | 2 inline→0, Badge | - | aria-hidden, focus rings |
| 8 | LiveIntelligenceFeed.tsx | 1 inline→0, 3 hex→tokens | TanStack Query | aria-hidden, error states |
| 9 | MetricRibbon.tsx | - | TanStack Query, todayStr | - |
| 10 | SidebarNav.tsx | 7 inline→0, Badge | - | aria-hidden, aria-labels, focus rings |

## Success Criteria

- Zero `style={{}}` blocks in target files (26 → 0)
- Zero hardcoded hex values in target files (23+ → 0)
- Zero redundant `fontFamily` declarations (13 → 0)
- TanStack Query replaces all `setInterval` polling
- All icon spans have `aria-hidden="true"`
- All icon-only buttons have `aria-label`
- All interactive elements have `focus-visible` rings
- `npx tsc --noEmit` passes
- `npm run build` succeeds

## Dependencies

- `@tanstack/react-query` (new install)
- No other new dependencies
