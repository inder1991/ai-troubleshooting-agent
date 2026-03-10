# Unified Design System & Performance Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate all inline styles, hardcoded hex values, and redundant fontFamily declarations from 6 dashboard components; migrate data fetching to TanStack Query; add accessibility fundamentals.

**Architecture:** Component-by-component sweep. Prerequisite tasks (Tailwind config, Badge, TanStack install) ship first, then each target file is swept individually with atomic commits.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, TanStack Query, Framer Motion

**Design Doc:** `docs/plans/2026-03-10-unified-design-system-design.md`

---

### Task 1: Extend Tailwind Config with Full Token Palette

**Files:**
- Modify: `frontend/tailwind.config.js`

**Step 1: Rewrite tailwind.config.js**

Replace the entire file with the approved config. This adds `duck-panel`, `duck-sidebar`, `duck-flyout`, `duck-muted` tokens, custom font sizes `micro`/`nano`, and the `pulse-amber` animation.

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        'primary':           '#07b6d5',
        'background-light':  '#f5f8f8',
        'background-dark':   '#0f2023',
        'neutral-slate':     '#1e2f33',
        'neutral-border':    '#224349',
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
        sans:    ['Inter', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
        mono:    ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        lg:      '0.5rem',
        xl:      '0.75rem',
        full:    '9999px',
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
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Build succeeds (no components use the new tokens yet, so nothing breaks)

**Step 3: Commit**

```bash
git add frontend/tailwind.config.js
git commit -m "feat(tokens): extend duck-* palette with panel/sidebar/flyout/muted + micro/nano fonts"
```

---

### Task 2: Create Reusable Badge Component

**Files:**
- Create: `frontend/src/components/ui/Badge.tsx`

**Step 1: Create Badge.tsx**

```tsx
import React from 'react';

export type BadgeType = 'NEW' | 'PREVIEW' | 'BETA';

interface BadgeProps {
  type: BadgeType;
  className?: string;
}

const styleMap: Record<BadgeType, string> = {
  NEW: 'bg-duck-accent/15 text-duck-accent border-duck-accent/30',
  PREVIEW: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  BETA: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
};

export const Badge: React.FC<BadgeProps> = ({ type, className = '' }) => (
  <span
    className={`inline-flex items-center justify-center px-1.5 py-0.5 rounded border text-nano font-black uppercase tracking-widest ${styleMap[type]} ${className}`}
  >
    {type}
  </span>
);

export default Badge;
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/ui/Badge.tsx
git commit -m "feat(ui): add reusable Badge component (NEW/PREVIEW/BETA)"
```

---

### Task 3: Install TanStack Query + Add QueryClientProvider

**Files:**
- Modify: `frontend/package.json` (via npm install)
- Modify: `frontend/src/App.tsx`

**Step 1: Install TanStack Query**

Run: `cd frontend && npm install @tanstack/react-query`

**Step 2: Add QueryClientProvider to App.tsx**

At the top of the file, add the import (after existing imports):

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
```

Before the `function App()` declaration, add:

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});
```

Update the `App` function to wrap with `QueryClientProvider`:

```tsx
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

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS (nothing uses useQuery yet)

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/App.tsx
git commit -m "feat(query): install TanStack Query and add QueryClientProvider"
```

---

### Task 4: Font Preload in index.html

**Files:**
- Modify: `frontend/index.html`

**Step 1: Add preload link before Material Symbols stylesheet**

The current Material Symbols link is on line 9. Add a preload hint directly before it:

Before:
```html
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
```

After:
```html
    <link rel="preload" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" as="style" />
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
```

**Step 2: Commit**

```bash
git add frontend/index.html
git commit -m "perf: add font preload hint for Material Symbols to reduce CLS"
```

---

### Task 5: HomePage.tsx — Token Sweep + a11y

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`

This file has 10 inline `style={{}}` blocks, 3 fontFamily declarations, and 8 hardcoded hex values.

**Step 1: Remove all inline styles and replace with Tailwind tokens**

Line 24 — outer wrapper div:
- Remove: `style={{ backgroundColor: '#0f2023' }}`
- Add class: `bg-duck-bg`

Line 26 — header element:
- Remove: `style={{ backgroundColor: 'rgba(15,32,35,0.5)', backdropFilter: 'blur(12px)' }}`
- Add classes: `bg-duck-panel/50 backdrop-blur-md`

Line 29 — system health badge:
- Remove: `style={{ backgroundColor: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}`
- Add classes: `bg-emerald-500/10 border border-emerald-500/20`

Line 40 — search icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

Line 44 — search input:
- Remove: `style={{ backgroundColor: 'rgba(30,47,51,0.4)', border: '1px solid #224349' }}`
- Add classes: `bg-duck-card/40 border border-duck-border`

Line 54 — notifications icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

Line 55 — notification dot:
- Remove: `style={{ backgroundColor: '#07b6d5', boxShadow: '0 0 0 2px #0f2023' }}`
- Add classes: `bg-duck-accent shadow-[0_0_0_2px_#0f2023]`
  (Note: Tailwind's `ring` could also work but `shadow-[...]` is more precise for the 2px outline effect)

Line 58 — vertical divider:
- Remove: `style={{ backgroundColor: '#224349' }}`
- Add class: `bg-duck-border`

Line 66 — user avatar div:
- Remove: `style={{ backgroundColor: 'rgba(7,182,213,0.2)' }}`
- Add class: `bg-duck-accent/20`

Line 67 — person icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}`
- Add class: `text-duck-accent`
- Add: `aria-hidden="true"`

**Step 2: Add aria-labels to icon-only buttons**

Notifications button: add `aria-label="View Notifications"`
Profile button: add `aria-label="User Profile"`

**Step 3: Add focus-visible rings to interactive elements**

Add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent` to:
- Notifications button
- Profile button
- Search input

**Step 4: Standardize transitions**

Ensure all interactive elements have `transition-all duration-200 ease-in-out` instead of inconsistent `transition-colors`.

**Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 6: Commit**

```bash
git add frontend/src/components/Home/HomePage.tsx
git commit -m "refactor(home): replace all inline styles with duck-* tokens, add a11y"
```

---

### Task 6: CapabilityLauncher.tsx — Token Sweep + Badge

**Files:**
- Modify: `frontend/src/components/Home/CapabilityLauncher.tsx`

This file has 6 inline `style={{}}` blocks, 2 fontFamily, and per-capability hex color data.

**Step 1: Convert capability data to Tailwind class strings**

Replace the hex-based `iconColor`, `iconBg`, `iconBorder`, `ctaColor` with Tailwind class strings:

```tsx
const capabilities = [
  {
    id: 'troubleshoot_app',
    title: 'App Diagnostic',
    // ...existing description, icon fields...
    iconClasses: 'text-duck-accent bg-duck-accent/10 border-duck-accent/20',
    ctaClasses: 'text-duck-accent',
    badge: null,
  },
  {
    id: 'pr_review',
    // ...
    iconClasses: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
    ctaClasses: 'text-indigo-400',
    badge: 'NEW' as const,
  },
  {
    id: 'github_issue_fix',
    // ...
    iconClasses: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    ctaClasses: 'text-amber-400',
    badge: null,
  },
  {
    id: 'cluster_diagnostics',
    // ...
    iconClasses: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    ctaClasses: 'text-emerald-400',
    badge: 'PREVIEW' as const,
  },
  {
    id: 'network_troubleshooting',
    // ...
    iconClasses: 'text-amber-500 bg-amber-500/[0.08] border-amber-500/20',
    ctaClasses: 'text-amber-500',
    badge: 'NEW' as const,
  },
];
```

**Step 2: Replace inline styles in card rendering**

Card wrapper (lines 89-92):
- Remove: `style={{ backgroundColor: 'rgba(30,47,51,0.2)', borderColor: '#224349' }}`
- Add classes: `bg-duck-card/20 border-duck-border`

Glow div (line 96):
- Remove: `style={{ backgroundColor: 'rgba(7,182,213,0.05)' }}`
- Add class: `bg-duck-accent/5`

Icon container (lines 101-103):
- Remove: `style={{ backgroundColor: cap.iconBg, borderColor: cap.iconBorder }}`
- Use: `className={`...border ${cap.iconClasses}`}` (class string from data)

Icon span (line 104):
- Remove: `style={{ fontFamily: 'Material Symbols Outlined', color: cap.iconColor }}`
- The color is now part of `iconClasses`. Add `aria-hidden="true"`.

CTA text (line 123):
- Remove: `style={{ color: cap.ctaColor }}`
- Use: `className={`... ${cap.ctaClasses}`}`

CTA arrow (line 126):
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

**Step 3: Replace inline badge with Badge component**

Replace lines 111-116:
```tsx
// OLD
{cap.badge && (
  <span className={`text-[8px] font-black px-1 py-0.5 rounded uppercase tracking-wider border ${...}`}>{cap.badge}</span>
)}

// NEW
import { Badge } from '../ui/Badge';
{cap.badge && <Badge type={cap.badge} />}
```

**Step 4: Add focus-visible and standardize transitions**

Add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent` and `transition-all duration-200 ease-in-out` to all card buttons.

**Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 6: Commit**

```bash
git add frontend/src/components/Home/CapabilityLauncher.tsx
git commit -m "refactor(caps): replace inline styles with duck-* tokens, use Badge component"
```

---

### Task 7: QuickActionsPanel.tsx — Token Sweep + Badge

**Files:**
- Modify: `frontend/src/components/Home/QuickActionsPanel.tsx`

2 inline `style={{}}` blocks, 2 fontFamily, 7 hardcoded hex values.

**Step 1: Replace all hardcoded hex values**

- `bg-[#0a1517]` → `bg-duck-panel`
- `border-[#224349]` → `border-duck-border`
- `hover:bg-[#162a2e]` → `hover:bg-duck-surface`
- `text-[#07b6d5]` → `text-duck-accent`
- `text-[#94a3b8]` → `text-duck-muted`

**Step 2: Remove fontFamily inline styles**

Line 28 — action icon span:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

Line 39 — arrow_forward icon span:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

**Step 3: Replace inline badge with Badge component**

Replace lines 32-38:
```tsx
// OLD
{a.badge && (
  <span className={`ml-2 text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider border ${...}`}>{a.badge}</span>
)}

// NEW
import { Badge } from '../ui/Badge';
{a.badge && <Badge type={a.badge} className="ml-2" />}
```

**Step 4: Add focus-visible and transitions**

Add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent` and `transition-all duration-200 ease-in-out` to all action buttons.

**Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 6: Commit**

```bash
git add frontend/src/components/Home/QuickActionsPanel.tsx
git commit -m "refactor(quick-actions): replace hex values with duck-* tokens, use Badge"
```

---

### Task 8: LiveIntelligenceFeed.tsx — TanStack Query + Token Sweep

**Files:**
- Modify: `frontend/src/components/Home/LiveIntelligenceFeed.tsx`

This is the main migration: replace `useEffect`/`setInterval` with `useQuery`.

**Step 1: Replace polling with TanStack Query**

Remove the entire `useEffect` block (current lines 48-63) and `useState` for `loading`.

Replace with:
```tsx
import { useQuery } from '@tanstack/react-query';

// Inside component:
const { data: sessions = [], isLoading, isError } = useQuery({
  queryKey: ['live-sessions'],
  queryFn: listSessionsV4,
  refetchInterval: 10000,
  staleTime: 5000,
});
```

Keep `onSessionsChange` callback — sync sessions to parent via useEffect:
```tsx
useEffect(() => {
  onSessionsChange(sessions);
}, [sessions, onSessionsChange]);
```

**Step 2: Add proper loading/error/empty states**

Replace the single empty state fallback with three discrete states:

Loading state:
```tsx
{isLoading && (
  <div className="space-y-2">
    {[1, 2, 3].map((i) => (
      <div key={i} className="h-16 rounded-md bg-duck-surface animate-pulse" style={{ opacity: 1 - i * 0.3 }} />
    ))}
  </div>
)}
```

Error state:
```tsx
{isError && !isLoading && (
  <div className="flex flex-col items-center justify-center h-64 text-center">
    <span className="material-symbols-outlined text-4xl text-red-500 mb-3" aria-hidden="true">wifi_off</span>
    <p className="text-sm font-semibold text-slate-300 mb-1">Feed Disconnected</p>
    <p className="text-xs text-slate-500">Failed to sync with the intelligence server. Retrying...</p>
  </div>
)}
```

Empty state (existing but with a11y):
```tsx
{!isLoading && !isError && sessions.length === 0 && (
  <div className="flex flex-col items-center justify-center h-64 text-center">
    <div className="w-16 h-16 rounded-full bg-duck-border/30 flex items-center justify-center mb-4">
      <span className="material-symbols-outlined text-2xl text-duck-accent" aria-hidden="true">satellite_alt</span>
    </div>
    <p className="text-sm font-semibold text-slate-300 mb-1">No Active Sessions</p>
    <p className="text-xs text-slate-500 max-w-sm mx-auto">Launch an investigation from Quick Actions to begin monitoring.</p>
  </div>
)}
```

**Step 3: Replace hardcoded hex values**

- `bg-[#0a1517]` → `bg-duck-panel`
- `border-[#224349]` → `border-duck-border`
- `border-[#07b6d5]` → `border-duck-accent`

**Step 4: Remove fontFamily**

Line 95 — empty state icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

**Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 6: Commit**

```bash
git add frontend/src/components/Home/LiveIntelligenceFeed.tsx
git commit -m "feat(feed): migrate to TanStack Query, replace inline styles with tokens"
```

---

### Task 9: MetricRibbon.tsx — TanStack Query + Performance Fix

**Files:**
- Modify: `frontend/src/components/Home/MetricRibbon.tsx`

**Step 1: Replace sessions prop with useQuery**

Remove the `MetricRibbonProps` interface and `sessions` prop. Self-fetch from query cache:

```tsx
import { useQuery } from '@tanstack/react-query';
import { listSessionsV4 } from '../../services/api';

export const MetricRibbon: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });
  // ...rest of component
```

**Step 2: Extract todayStr outside the loop**

Move `new Date().toDateString()` to module-level or before useMemo:

```tsx
const todayStr = new Date().toDateString();

const isResolvedToday = (s: V4Session) => {
  if (!['complete', 'diagnosis_complete'].includes(s.status)) return false;
  return new Date(s.updated_at).toDateString() === todayStr;
};
```

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/components/Home/MetricRibbon.tsx
git commit -m "feat(ribbon): migrate to TanStack Query, extract todayStr for perf"
```

---

### Task 10: HomePage.tsx — Remove Prop Drilling

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`
- Modify: `frontend/src/App.tsx`

Now that LiveIntelligenceFeed and MetricRibbon self-fetch via useQuery, remove prop drilling.

**Step 1: Remove sessions/onSessionsChange from HomePage props**

```tsx
interface HomePageProps {
  onSelectCapability: (capability: CapabilityType) => void;
  onSelectSession: (session: V4Session) => void;
  wsConnected: boolean;
  // REMOVED: sessions, onSessionsChange
}
```

Update the JSX to remove the props from child components:
- `<MetricRibbon />` (no props needed)
- `<LiveIntelligenceFeed onSelectSession={onSelectSession} />` (keep onSelectSession, remove onSessionsChange)

**Step 2: Update App.tsx call site**

Find where `<HomePage>` is rendered in App.tsx and remove the `sessions={sessions}` and `onSessionsChange={setSessions}` props.

**Note:** If `sessions` state in App.tsx is still needed elsewhere (e.g., for conditional rendering), keep the useState but don't pass it to HomePage. If it's only used by HomePage children, remove it entirely.

**Step 3: Update LiveIntelligenceFeed props**

Remove `onSessionsChange` from the component's props interface. Remove the `useEffect` that syncs sessions to parent. The component now only exposes `onSelectSession`.

```tsx
interface LiveIntelligenceFeedProps {
  onSelectSession: (session: V4Session) => void;
  // REMOVED: onSessionsChange
}
```

**Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 5: Commit**

```bash
git add frontend/src/components/Home/HomePage.tsx frontend/src/App.tsx frontend/src/components/Home/LiveIntelligenceFeed.tsx frontend/src/components/Home/MetricRibbon.tsx
git commit -m "refactor(home): remove sessions prop drilling, children self-fetch via React Query"
```

---

### Task 11: SidebarNav.tsx — Token Sweep + a11y

**Files:**
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`

7 inline `style={{}}` blocks, 5 fontFamily declarations, multiple hardcoded hex values.

**Step 1: Fix the `iconEl` helper (line 83)**

Current:
```tsx
const iconEl = (icon: string, size = 19) => (
  <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined', fontSize: size }}>
    {icon}
  </span>
);
```

Replace with:
```tsx
const iconEl = (icon: string, size = 19) => (
  <span
    className="material-symbols-outlined transition-colors duration-200"
    style={{ fontSize: size }}
    aria-hidden="true"
  >
    {icon}
  </span>
);
```

(Keep `fontSize` as inline style since it's a dynamic numeric prop. Remove `fontFamily`.)

**Step 2: Replace hardcoded hex values**

- `bg-[#000000]` → `bg-duck-sidebar`
- `border-[#1a1a1a]` → `border-duck-sidebar` (or define a new token; `#1a1a1a` is close to sidebar. Since it's a subtle border on a black sidebar, use `border-white/5` for a more semantic approach)
- `bg-[#090909]/95` → `bg-duck-flyout/95`
- `style={{ backgroundColor: '#07b6d5', color: '#0c1a1e' }}` on New Mission button → `bg-duck-accent text-duck-bg`

**Step 3: Remove remaining fontFamily inline styles**

Line 183 — brand icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}`
- Add class: `text-duck-accent`
- Add: `aria-hidden="true"`

Lines 248-252 — group chevron:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined', fontSize: 15 }}`
- Keep only: `style={{ fontSize: 15 }}`
- Add: `aria-hidden="true"`

Line 266 — New Mission button:
- Remove: `style={{ backgroundColor: '#07b6d5', color: '#0c1a1e', boxShadow: '0 2px 12px rgba(7,182,213,0.15)' }}`
- Add classes: `bg-duck-accent text-duck-bg shadow-[0_2px_12px_rgba(7,182,213,0.15)]`

Line 269 — add_circle icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

Lines 305-307 — pin icon:
- Remove: `style={{ fontFamily: 'Material Symbols Outlined' }}`
- Add: `aria-hidden="true"`

**Step 4: Import and use Badge component**

Find where "NEW" and "PREVIEW" badge spans exist in SidebarNav and replace with `<Badge>` component.

**Step 5: Add aria-labels and focus-visible**

- New Mission button: `aria-label="Start New Mission"`
- All nav link buttons: `aria-label={item.label}`
- Add `focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent` to all buttons

**Step 6: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 7: Commit**

```bash
git add frontend/src/components/Layout/SidebarNav.tsx
git commit -m "refactor(sidebar): replace all inline styles with duck-* tokens, add a11y"
```

---

### Task 12: Final Verification

**Files:** None (verification only)

**Step 1: Run full frontend build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Zero errors, successful build

**Step 2: Audit for remaining inline styles**

Run a grep across all target files to verify zero remaining `style={{` blocks (except legitimate dynamic sizing like `fontSize`):

```bash
grep -n 'style={{' frontend/src/components/Home/HomePage.tsx frontend/src/components/Home/CapabilityLauncher.tsx frontend/src/components/Home/QuickActionsPanel.tsx frontend/src/components/Home/LiveIntelligenceFeed.tsx frontend/src/components/Home/MetricRibbon.tsx frontend/src/components/Layout/SidebarNav.tsx
```

Expected: Only `fontSize` dynamic props remain in SidebarNav's `iconEl` and chevron.

**Step 3: Audit for remaining fontFamily**

```bash
grep -n 'fontFamily' frontend/src/components/Home/HomePage.tsx frontend/src/components/Home/CapabilityLauncher.tsx frontend/src/components/Home/QuickActionsPanel.tsx frontend/src/components/Home/LiveIntelligenceFeed.tsx frontend/src/components/Home/MetricRibbon.tsx frontend/src/components/Layout/SidebarNav.tsx
```

Expected: Zero matches

**Step 4: Audit for remaining hardcoded hex**

```bash
grep -n '#0f2023\|#0a1517\|#224349\|#07b6d5\|#94a3b8\|#000000\|#090909\|#0c1a1e' frontend/src/components/Home/HomePage.tsx frontend/src/components/Home/CapabilityLauncher.tsx frontend/src/components/Home/QuickActionsPanel.tsx frontend/src/components/Home/LiveIntelligenceFeed.tsx frontend/src/components/Layout/SidebarNav.tsx
```

Expected: Zero matches (hex values only exist in tailwind.config.js)

**Step 5: Run backend tests to confirm no regressions**

Run: `cd backend && python3 -m pytest tests/ -x -q`
Expected: All pass

---

## Dependency Graph

```
Phase 1 (Prereqs):
  Task 1 (Tailwind Config)
  Task 2 (Badge Component)

Phase 2 (Infrastructure):
  Task 3 (TanStack Query Install)
  Task 4 (Font Preload)

Phase 3 (Component Sweep):
  Task 5 (HomePage) ←── Tasks 1
  Task 6 (CapabilityLauncher) ←── Tasks 1, 2
  Task 7 (QuickActionsPanel) ←── Tasks 1, 2
  Task 8 (LiveIntelligenceFeed) ←── Tasks 1, 3
  Task 9 (MetricRibbon) ←── Tasks 3
  Task 10 (Prop Drilling Cleanup) ←── Tasks 8, 9
  Task 11 (SidebarNav) ←── Tasks 1, 2

Phase 4 (Verification):
  Task 12 (Final Verification) ←── ALL
```

## New Dependencies

```bash
npm install @tanstack/react-query
```

No other new dependencies required.
