# Path-Based Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the frontend's `viewState` string-based navigation with React Router v6 path-based routing, enabling deep linking, bookmarking, browser history, and self-sufficient view components.

**Architecture:** Install `react-router-dom` v6, create a nested route config under a root `AppLayout` with `<Outlet>`, add a compatibility adapter (`NavigationContext`) so existing components work during migration, then incrementally migrate each section to use `useParams()` and `useNavigate()` instead of prop-drilled callbacks.

**Tech Stack:** React Router v6, React 18, TypeScript 5.3, Vite 5, Tailwind CSS 3.4

---

## Phase 1: Foundation

### Task 1: Install react-router-dom

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install the dependency**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npm install react-router-dom@6`

**Step 2: Verify installation**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && node -e "require('react-router-dom')"`
Expected: No error

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add package.json package-lock.json
git commit -m "chore: install react-router-dom v6"
```

---

### Task 2: Create NotFound page

**Files:**
- Create: `frontend/src/pages/NotFound.tsx`

**Step 1: Create the NotFound component**

```tsx
import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 text-slate-300">
      <span
        className="material-symbols-outlined text-7xl text-slate-500"
        aria-hidden="true"
      >
        explore_off
      </span>
      <h1 className="text-2xl font-display font-bold text-slate-100">
        Page not found
      </h1>
      <p className="text-sm text-slate-400 max-w-md text-center">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Link
        to="/"
        className="px-4 py-2 rounded-lg bg-duck-accent/20 text-duck-accent text-sm font-medium hover:bg-duck-accent/30 transition-colors"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`
Expected: No errors (or only pre-existing ones unrelated to NotFound)

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/pages/NotFound.tsx
git commit -m "feat(routing): add NotFound 404 page"
```

---

### Task 3: Create NavigationContext compatibility adapter

This context bridges old `onNavigate(view)` callbacks to React Router's `useNavigate()`. During migration, components that still use `onNavigate` can call `navContext.navigate(navView)` and it translates to a URL push. Once all components are migrated, this context gets removed.

**Files:**
- Create: `frontend/src/contexts/NavigationContext.tsx`

**Step 1: Create the context**

```tsx
import { createContext, useContext, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type { NavView } from '../components/Layout/SidebarNav';

/**
 * Maps legacy NavView string IDs to URL paths.
 * Used by the compatibility adapter during incremental migration.
 */
const NAV_VIEW_TO_PATH: Record<string, string> = {
  home: '/',
  sessions: '/investigations',
  'how-it-works': '/how-it-works',
  // Diagnostics — form-triggering views
  'app-diagnostics': '/investigations/new?capability=troubleshoot_app',
  'k8s-diagnostics': '/investigations/new?capability=cluster_diagnostics',
  'network-troubleshooting': '/investigations/new?capability=network_troubleshooting',
  'pr-review': '/investigations/new?capability=pr_review',
  'github-issue-fix': '/investigations/new?capability=github_issue_fix',
  'db-diagnostics': '/investigations/new?capability=database_diagnostics',
  // Network
  'network-topology': '/network/topology',
  'network-adapters': '/network/adapters',
  'device-monitoring': '/network/monitoring',
  ipam: '/network/ipam',
  matrix: '/network/flows',
  observatory: '/network/observatory',
  'mib-browser': '/network/mib-browser',
  'live-topology': '/network/live-topology',
  // Database
  'db-overview': '/database',
  'db-connections': '/database/connections',
  'db-monitoring': '/database/monitoring',
  'db-schema': '/database/schema',
  'db-operations': '/database/operations',
  // Clusters
  'k8s-clusters': '/clusters',
  'cluster-registry': '/clusters/registry',
  'cluster-recommendations': '/clusters/recommendations',
  // Agents
  'agent-matrix': '/agents/matrix',
  'agent-catalog': '/agents',
  // Workflows
  'workflow-builder': '/workflows',
  'workflow-runs': '/workflows/runs',
  // Settings
  integrations: '/settings/integrations',
  settings: '/settings',
  'audit-log': '/audit',
  // Cloud & Security
  'cloud-resources': '/network/cloud',
  'security-resources': '/network/security',
};

interface NavigationContextType {
  /** Navigate using a legacy NavView id — translates to URL push */
  navigateByView: (view: NavView) => void;
  /** Get the URL path for a NavView id */
  getPath: (view: NavView) => string;
}

const NavigationContext = createContext<NavigationContextType | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  const navigateByView = useCallback(
    (view: NavView) => {
      const path = NAV_VIEW_TO_PATH[view] ?? '/';
      navigate(path);
    },
    [navigate],
  );

  const getPath = useCallback((view: NavView) => {
    return NAV_VIEW_TO_PATH[view] ?? '/';
  }, []);

  const value = useMemo(
    () => ({ navigateByView, getPath }),
    [navigateByView, getPath],
  );

  return (
    <NavigationContext.Provider value={value}>
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation() {
  const ctx = useContext(NavigationContext);
  if (!ctx) throw new Error('useNavigation must be used within NavigationProvider');
  return ctx;
}

export { NAV_VIEW_TO_PATH };
export default NavigationContext;
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`
Expected: No errors related to NavigationContext

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/contexts/NavigationContext.tsx
git commit -m "feat(routing): add NavigationContext compatibility adapter"
```

---

### Task 4: Create AppLayout root layout component

This is the root layout rendered by the router. It renders the sidebar + breadcrumbs + `<Outlet>` for child routes. Investigation/war-room routes hide the sidebar.

**Files:**
- Create: `frontend/src/layouts/AppLayout.tsx`

**Step 1: Create the layout**

```tsx
import { Outlet, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import SidebarNav from '../components/Layout/SidebarNav';
import { useNavigation } from '../contexts/NavigationContext';
import { Breadcrumbs } from '../components/shared';

/** Paths where the sidebar is hidden (war-room / full-screen views) */
const SIDEBAR_HIDDEN_PATHS = [
  '/investigations/',  // active investigation (has :sessionId)
  '/network/live-topology',
];

function shouldHideSidebar(pathname: string): boolean {
  // Exact match for live-topology
  if (pathname === '/network/live-topology') return true;
  // Investigation routes with a session ID (but not the list)
  if (pathname.startsWith('/investigations/') && pathname !== '/investigations/') return true;
  return false;
}

export default function AppLayout() {
  const location = useLocation();
  const { navigateByView } = useNavigation();
  const showSidebar = !shouldHideSidebar(location.pathname);

  // Pin-responsive layout
  const [isSidebarPinned, setIsSidebarPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });

  useEffect(() => {
    const handlePinChange = () => {
      try { setIsSidebarPinned(localStorage.getItem('sidebar-pinned') === 'true'); } catch { /* noop */ }
    };
    window.addEventListener('sidebar-pin-change', handlePinChange);
    return () => window.removeEventListener('sidebar-pin-change', handlePinChange);
  }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased command-center-bg">
      {showSidebar && (
        <SidebarNav
          activeView="home"
          onNavigate={navigateByView}
          onNewMission={() => navigateByView('home')}
        />
      )}

      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && isSidebarPinned ? 215 : 0 }}
      >
        <Outlet />
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`
Expected: No errors related to AppLayout

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/AppLayout.tsx
git commit -m "feat(routing): add AppLayout root layout with sidebar + Outlet"
```

---

### Task 5: Create router configuration

Central route config file. All routes defined here. During migration, most routes render the existing components directly — they don't need to be self-sufficient yet (that comes in later phases).

**Files:**
- Create: `frontend/src/router.tsx`

**Step 1: Create the router config**

```tsx
import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './layouts/AppLayout';
import NotFound from './pages/NotFound';

// Existing page components — imported as-is during migration
import HomePage from './components/Home/HomePage';
import HowItWorksView from './components/HowItWorks/HowItWorksView';
import SessionManagerView from './components/Sessions/SessionManagerView';
import CapabilityForm from './components/ActionCenter/CapabilityForm';
import TopologyEditorView from './components/TopologyEditor/TopologyEditorView';
import NetworkAdaptersView from './components/Network/NetworkAdaptersView';
import DeviceMonitoring from './components/Network/DeviceMonitoring';
import IPAMDashboard from './components/IPAM/IPAMDashboard';
import ReachabilityMatrix from './components/NetworkTroubleshooting/ReachabilityMatrix';
import ObservatoryView from './components/Observatory/ObservatoryView';
import FullScreenTopology from './components/Observatory/topology/FullScreenTopology';
import MIBBrowserView from './components/Network/MIBBrowserView';
import CloudResourcesView from './components/Cloud/CloudResourcesView';
import SecurityResourcesView from './components/Security/SecurityResourcesView';
import DBOverview from './components/Database/DBOverview';
import DBConnections from './components/Database/DBConnections';
import DBDiagnosticsPage from './components/Database/DBDiagnosticsPage';
import DBMonitoring from './components/Database/DBMonitoring';
import DBSchema from './components/Database/DBSchema';
import DBOperations from './components/Database/DBOperations';
import KubernetesClusters from './components/Kubernetes/KubernetesClusters';
import ClusterRegistryPage from './components/ClusterRegistry/ClusterRegistryPage';
import ClusterRecommendationsPage from './components/ClusterRegistry/ClusterRecommendationsPage';
import AgentMatrixView from './components/AgentMatrix/AgentMatrixView';
import AgentCatalogView from './components/Platform/AgentCatalog/AgentCatalogView';
import WorkflowBuilderView from './components/Platform/WorkflowBuilder/WorkflowBuilderView';
import WorkflowRunsView from './components/Platform/WorkflowRuns/WorkflowRunsView';
import IntegrationSettings from './components/Settings/IntegrationSettings';
import SettingsView from './components/Settings/SettingsView';
import AuditLogView from './components/AuditLog/AuditLogView';

/**
 * Wrapper components that adapt existing components to work as route elements.
 * These are temporary — they'll be replaced when each component becomes self-sufficient.
 */

function HomeRoute() {
  // HomePage needs callbacks — provide stubs that use navigation context
  // Full wiring happens in Phase 2 when we migrate investigations
  return <HomePage onSelectCapability={() => {}} onSelectSession={() => {}} wsConnected={false} />;
}

function HowItWorksRoute() {
  return <HowItWorksView onGoHome={() => {}} />;
}

function SessionsRoute() {
  return <SessionManagerView sessions={[]} onSessionsChange={() => {}} onSelectSession={() => {}} />;
}

function ObservatoryRoute() {
  return <ObservatoryView onOpenEditor={() => {}} onOpenTopology={() => {}} />;
}

function LiveTopologyRoute() {
  return <FullScreenTopology onGoBack={() => {}} />;
}

function AgentMatrixRoute() {
  return <AgentMatrixView onGoHome={() => {}} />;
}

function IntegrationsRoute() {
  return <IntegrationSettings onBack={() => {}} />;
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomeRoute /> },
      { path: 'how-it-works', element: <HowItWorksRoute /> },

      // Investigations — Phase 2 will make these self-sufficient
      { path: 'investigations', element: <SessionsRoute /> },
      // investigations/:sessionId and investigations/:sessionId/dossier added in Phase 2
      // investigations/new (capability form) added in Phase 2

      // Network section
      { path: 'network/topology', element: <TopologyEditorView /> },
      { path: 'network/adapters', element: <NetworkAdaptersView /> },
      { path: 'network/monitoring', element: <DeviceMonitoring /> },
      { path: 'network/ipam', element: <IPAMDashboard /> },
      { path: 'network/flows', element: <ReachabilityMatrix /> },
      { path: 'network/observatory', element: <ObservatoryRoute /> },
      { path: 'network/live-topology', element: <LiveTopologyRoute /> },
      { path: 'network/mib-browser', element: <MIBBrowserView /> },
      { path: 'network/cloud', element: <CloudResourcesView /> },
      { path: 'network/security', element: <SecurityResourcesView /> },

      // Database section
      { path: 'database', element: <DBOverview /> },
      { path: 'database/connections', element: <DBConnections /> },
      { path: 'database/diagnostics', element: <DBDiagnosticsPage /> },
      { path: 'database/monitoring', element: <DBMonitoring /> },
      { path: 'database/schema', element: <DBSchema /> },
      { path: 'database/operations', element: <DBOperations /> },

      // Clusters section
      { path: 'clusters', element: <KubernetesClusters /> },
      { path: 'clusters/registry', element: <ClusterRegistryPage onViewRecommendations={() => {}} onRunScan={() => {}} /> },
      { path: 'clusters/recommendations', element: <ClusterRecommendationsPage clusterId="" onBack={() => {}} /> },

      // Agents section
      { path: 'agents', element: <AgentCatalogView /> },
      { path: 'agents/matrix', element: <AgentMatrixRoute /> },

      // Workflows section
      { path: 'workflows', element: <WorkflowBuilderView /> },
      { path: 'workflows/runs', element: <WorkflowRunsView onNavigate={() => {}} /> },

      // Settings section
      { path: 'settings', element: <SettingsView /> },
      { path: 'settings/integrations', element: <IntegrationsRoute /> },

      // Audit
      { path: 'audit', element: <AuditLogView /> },

      // 404
      { path: '*', element: <NotFound /> },
    ],
  },
]);
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`
Expected: No errors related to router.tsx

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/router.tsx
git commit -m "feat(routing): add central route configuration with all views"
```

---

### Task 6: Update main.tsx to use the router

Replace the simple `<App />` render with `<RouterProvider>`. The old `App.tsx` is **not deleted** yet — it stays as reference during migration. The router now controls what renders.

**Files:**
- Modify: `frontend/src/main.tsx`

**Step 1: Update main.tsx**

Replace the entire file with:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './components/Toast/ToastContext';
import { router } from './router';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`
Expected: No errors

**Step 3: Verify dev server starts**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx vite --host 0.0.0.0 &`
Then visit `http://localhost:5173/` — should render the dashboard.
Visit `http://localhost:5173/bad-path` — should render 404 page.
Kill the dev server.

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/main.tsx
git commit -m "feat(routing): wire RouterProvider in main.tsx entry point"
```

---

### Task 7: Update AppLayout to integrate NavigationProvider

The `AppLayout` needs to be wrapped with `NavigationProvider` so that child components can call `useNavigation()`. But `NavigationProvider` needs to be **inside** the router (it uses `useNavigate()`), so it wraps `AppLayout`'s children.

**Files:**
- Modify: `frontend/src/layouts/AppLayout.tsx`

**Step 1: Wrap Outlet with NavigationProvider**

In `AppLayout.tsx`, add the import and wrap:

```tsx
import { NavigationProvider } from '../contexts/NavigationContext';
```

Then wrap the return JSX: the `NavigationProvider` must wrap the entire component body since `SidebarNav` also uses `navigateByView`.

Update the component to:

```tsx
export default function AppLayout() {
  const location = useLocation();
  const showSidebar = !shouldHideSidebar(location.pathname);

  // Pin-responsive layout
  const [isSidebarPinned, setIsSidebarPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });

  useEffect(() => {
    const handlePinChange = () => {
      try { setIsSidebarPinned(localStorage.getItem('sidebar-pinned') === 'true'); } catch { /* noop */ }
    };
    window.addEventListener('sidebar-pin-change', handlePinChange);
    return () => window.removeEventListener('sidebar-pin-change', handlePinChange);
  }, []);

  return (
    <NavigationProvider>
      <AppLayoutInner showSidebar={showSidebar} isSidebarPinned={isSidebarPinned} />
    </NavigationProvider>
  );
}

function AppLayoutInner({ showSidebar, isSidebarPinned }: { showSidebar: boolean; isSidebarPinned: boolean }) {
  const { navigateByView } = useNavigation();

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased command-center-bg">
      {showSidebar && (
        <SidebarNav
          activeView="home"
          onNavigate={navigateByView}
          onNewMission={() => navigateByView('home')}
        />
      )}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && isSidebarPinned ? 215 : 0 }}
      >
        <Outlet />
      </div>
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/AppLayout.tsx
git commit -m "feat(routing): integrate NavigationProvider in AppLayout"
```

---

### Task 8: Update AppLayout sidebar to derive activeView from URL

The sidebar needs to highlight the correct nav item based on the current URL path, not a hardcoded `"home"`.

**Files:**
- Modify: `frontend/src/layouts/AppLayout.tsx`
- Modify: `frontend/src/contexts/NavigationContext.tsx` (add reverse lookup)

**Step 1: Add PATH_TO_NAV_VIEW reverse map to NavigationContext**

In `NavigationContext.tsx`, add after `NAV_VIEW_TO_PATH`:

```tsx
/**
 * Reverse map: URL pathname → NavView.
 * Built from NAV_VIEW_TO_PATH, stripping query strings.
 */
const PATH_TO_NAV_VIEW: Record<string, NavView> = {};
for (const [view, path] of Object.entries(NAV_VIEW_TO_PATH)) {
  const cleanPath = path.split('?')[0];
  PATH_TO_NAV_VIEW[cleanPath] = view as NavView;
}

export function pathToNavView(pathname: string): NavView {
  return PATH_TO_NAV_VIEW[pathname] ?? 'home';
}
```

Export `pathToNavView` from the file.

**Step 2: Use pathToNavView in AppLayoutInner**

In `AppLayout.tsx`, update `AppLayoutInner` to derive `activeView`:

```tsx
import { useNavigation, pathToNavView } from '../contexts/NavigationContext';
import { useLocation } from 'react-router-dom';

function AppLayoutInner({ showSidebar, isSidebarPinned }: { showSidebar: boolean; isSidebarPinned: boolean }) {
  const { navigateByView } = useNavigation();
  const location = useLocation();
  const activeView = pathToNavView(location.pathname);

  return (
    <div className="flex h-screen w-full overflow-hidden text-slate-100 antialiased command-center-bg">
      {showSidebar && (
        <SidebarNav
          activeView={activeView}
          onNavigate={navigateByView}
          onNewMission={() => navigateByView('home')}
        />
      )}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden transition-all duration-300 ease-out"
        style={{ paddingLeft: showSidebar && isSidebarPinned ? 215 : 0 }}
      >
        <Outlet />
      </div>
    </div>
  );
}
```

**Step 3: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/AppLayout.tsx src/contexts/NavigationContext.tsx
git commit -m "feat(routing): derive sidebar activeView from URL pathname"
```

---

### Task 9: Wire route wrappers to use NavigationContext for callbacks

The route wrapper functions in `router.tsx` currently pass `() => {}` stubs. Update them to use `useNavigation()` so callbacks like `onGoHome`, `onBack`, `onOpenEditor`, etc. actually navigate.

**Files:**
- Modify: `frontend/src/router.tsx`

**Step 1: Update route wrapper functions**

Replace the stub wrapper functions with:

```tsx
import { useNavigation } from './contexts/NavigationContext';
import { useNavigate } from 'react-router-dom';

function HomeRoute() {
  const navigate = useNavigate();
  const { navigateByView } = useNavigation();
  return (
    <HomePage
      onSelectCapability={(cap) => navigate(`/investigations/new?capability=${cap}`)}
      onSelectSession={(session) => navigate(`/investigations/${session.session_id}`)}
      wsConnected={false}
    />
  );
}

function HowItWorksRoute() {
  const navigate = useNavigate();
  return <HowItWorksView onGoHome={() => navigate('/')} />;
}

function SessionsRoute() {
  const navigate = useNavigate();
  return (
    <SessionManagerView
      sessions={[]}
      onSessionsChange={() => {}}
      onSelectSession={(session) => navigate(`/investigations/${session.session_id}`)}
    />
  );
}

function ObservatoryRoute() {
  const navigate = useNavigate();
  return (
    <ObservatoryView
      onOpenEditor={() => navigate('/network/topology')}
      onOpenTopology={() => navigate('/network/live-topology')}
    />
  );
}

function LiveTopologyRoute() {
  const navigate = useNavigate();
  return <FullScreenTopology onGoBack={() => navigate('/network/observatory')} />;
}

function AgentMatrixRoute() {
  const navigate = useNavigate();
  return <AgentMatrixView onGoHome={() => navigate('/')} />;
}

function IntegrationsRoute() {
  const navigate = useNavigate();
  return <IntegrationSettings onBack={() => navigate('/')} />;
}

function ClusterRegistryRoute() {
  const navigate = useNavigate();
  return (
    <ClusterRegistryPage
      onViewRecommendations={(id) => navigate(`/clusters/recommendations?clusterId=${id}`)}
      onRunScan={() => {}}
    />
  );
}

function ClusterRecommendationsRoute() {
  const navigate = useNavigate();
  const params = new URLSearchParams(window.location.search);
  const clusterId = params.get('clusterId') || '';
  return (
    <ClusterRecommendationsPage
      clusterId={clusterId}
      onBack={() => navigate('/clusters/registry')}
    />
  );
}

function WorkflowRunsRoute() {
  const navigate = useNavigate();
  return <WorkflowRunsView onNavigate={(v) => navigate(`/workflows/${v === 'workflow-builder' ? '' : v}`)} />;
}
```

Then update the route config to use the new wrapper components for clusters and workflow-runs:

```tsx
{ path: 'clusters/registry', element: <ClusterRegistryRoute /> },
{ path: 'clusters/recommendations', element: <ClusterRecommendationsRoute /> },
{ path: 'workflows/runs', element: <WorkflowRunsRoute /> },
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 3: Verify dev server — navigate between views**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx vite --host 0.0.0.0 &`
- Visit `http://localhost:5173/` — dashboard renders
- Click sidebar items — URL changes, correct view renders
- Visit `http://localhost:5173/network/topology` directly — topology view renders
- Visit `http://localhost:5173/settings` — settings view renders
- Visit `http://localhost:5173/foo` — 404 page renders
- Browser back/forward buttons work
Kill the dev server.

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/router.tsx
git commit -m "feat(routing): wire route wrappers with NavigationContext callbacks"
```

---

### Task 10: Add Vite historyApiFallback for SPA routing

Vite dev server already handles this by default, but we need to ensure the production build also serves `index.html` for all routes. Add a note in `vite.config.ts` if needed. Actually, Vite dev server handles SPA fallback automatically. For production, the hosting platform (nginx, etc.) handles it. No code change needed — just verify.

**Step 1: Verify Vite dev server handles SPA fallback**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx vite --host 0.0.0.0 &`
Visit `http://localhost:5173/network/topology` directly (not via navigation).
Expected: The page renders correctly, not a 404.
Kill the dev server.

**Step 2: Verify production build**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npm run build`
Expected: Build succeeds. Output in `dist/` contains `index.html`.

**Step 3: Commit (if any config changes needed)**

No commit needed if Vite handles it automatically.

---

## Phase 2: Migrate Investigations (Highest Value)

### Task 11: Create CapabilityForm route with URL query param

The capability form is triggered by `/investigations/new?capability=<type>`. The form reads the capability from the URL search params.

**Files:**
- Modify: `frontend/src/router.tsx`

**Step 1: Create CapabilityFormRoute wrapper**

```tsx
import { useSearchParams } from 'react-router-dom';
import type { CapabilityType, CapabilityFormData } from './types';
import { startSessionV4, API_BASE_URL } from './services/api';

function CapabilityFormRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const capability = searchParams.get('capability') as CapabilityType | null;

  if (!capability) {
    return <NotFound />;
  }

  const handleSubmit = async (data: CapabilityFormData) => {
    try {
      // Simplified session creation — delegates to API, then navigates to investigation
      const session = await startSessionV4({
        service_name: data.service_name || capability,
        time_window: (data as any).time_window || '1h',
        capability,
      });
      navigate(`/investigations/${session.session_id}`);
    } catch (err) {
      console.error('Failed to start session:', err);
    }
  };

  return (
    <CapabilityForm
      capability={capability}
      onBack={() => navigate('/')}
      onSubmit={handleSubmit}
    />
  );
}
```

Add route:
```tsx
{ path: 'investigations/new', element: <CapabilityFormRoute /> },
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/router.tsx
git commit -m "feat(routing): add /investigations/new capability form route"
```

---

### Task 12: Create InvestigationRoute — self-sufficient investigation view

This is the most complex route. It reads `sessionId` from URL params, fetches session status + findings, connects WebSocket, and renders the full investigation war room.

**Files:**
- Create: `frontend/src/pages/InvestigationRoute.tsx`
- Modify: `frontend/src/router.tsx`

**Step 1: Create the route component**

```tsx
import { useParams, useNavigate } from 'react-router-dom';
import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  V4Session,
  TaskEvent,
  DiagnosticPhase,
  TokenUsage,
  ChatMessage,
  AttestationGateData,
} from '../types';
import { useWebSocketV4 } from '../hooks/useWebSocket';
import type { ChatStreamEndPayload } from '../hooks/useWebSocket';
import { getSessionStatus, submitAttestation } from '../services/api';
import { useToast } from '../components/Toast/ToastContext';
import { ChatProvider } from '../contexts/ChatContext';
import { CampaignProvider } from '../contexts/CampaignContext';
import ForemanHUD from '../components/Foreman/ForemanHUD';
import InvestigationView from '../components/Investigation/InvestigationView';
import DatabaseWarRoom from '../components/Investigation/DatabaseWarRoom';
import ClusterWarRoom from '../components/ClusterDiagnostic/ClusterWarRoom';
import NetworkWarRoom from '../components/NetworkTroubleshooting/NetworkWarRoom';
import ErrorBoundary from '../components/ui/ErrorBoundary';
import ErrorBanner from '../components/ui/ErrorBanner';

export default function InvestigationRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();

  const [session, setSession] = useState<V4Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskEvents, setTaskEvents] = useState<TaskEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage[]>([]);
  const [attestationGate, setAttestationGate] = useState<AttestationGateData | null>(null);
  const [wsMaxReconnectsHit, setWsMaxReconnectsHit] = useState(false);

  // Fetch session on mount
  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    getSessionStatus(sessionId)
      .then((status) => {
        setSession({
          session_id: sessionId,
          service_name: status.service_name || 'Investigation',
          status: status.phase,
          confidence: status.confidence,
          created_at: status.created_at || new Date().toISOString(),
          updated_at: status.updated_at || new Date().toISOString(),
          incident_id: status.incident_id || '',
          capability: status.capability || 'troubleshoot_app',
        });
        setCurrentPhase(status.phase);
        setConfidence(status.confidence);
        setTokenUsage(status.token_usage);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Session not found');
        setLoading(false);
      });
  }, [sessionId]);

  // Refresh session status
  const refreshStatus = useCallback(async () => {
    if (!sessionId) return;
    try {
      const status = await getSessionStatus(sessionId);
      setCurrentPhase(status.phase);
      setConfidence(status.confidence);
      setTokenUsage(status.token_usage);
    } catch { /* silent */ }
  }, [sessionId]);

  // WebSocket handlers
  const handleTaskEvent = useCallback(
    (event: TaskEvent) => {
      setTaskEvents((prev) => {
        const updated = [...prev, event];
        return updated.length > 500 ? updated.slice(-500) : updated;
      });

      if (event.event_type === 'phase_change' && event.details?.phase) {
        setCurrentPhase(event.details.phase as DiagnosticPhase);
      }
      if (event.event_type === 'summary' && event.details?.confidence != null) {
        setConfidence(event.details.confidence as number);
      }
      if (event.event_type === 'attestation_required' && event.details) {
        setAttestationGate({
          gate_type: event.details.gate_type as AttestationGateData['gate_type'],
          human_decision: null,
          decided_by: null,
          decided_at: null,
          proposed_action: event.details.proposed_action as string,
          findings_count: event.details.findings_count as number,
          confidence: event.details.confidence as number,
        });
      }
      if (['summary', 'finding', 'phase_change', 'success', 'waiting_for_input'].includes(event.event_type)) {
        refreshStatus();
      }
    },
    [refreshStatus],
  );

  // Chat response bridging
  const chatResponseRef = useRef<((msg: ChatMessage) => void) | null>(null);
  const handleChatResponse = useCallback((message: ChatMessage) => {
    chatResponseRef.current?.(message);
  }, []);

  const streamStartRef = useRef<(() => void) | null>(null);
  const streamAppendRef = useRef<((chunk: string) => void) | null>(null);
  const streamFinishRef = useRef<((full: string, meta?: ChatMessage['metadata']) => void) | null>(null);

  const handleChatChunk = useCallback((chunk: string) => {
    streamStartRef.current?.();
    streamAppendRef.current?.(chunk);
  }, []);

  const handleChatStreamEnd = useCallback((payload: ChatStreamEndPayload) => {
    const meta: ChatMessage['metadata'] = {};
    if (payload.phase) {
      meta.newPhase = payload.phase;
      meta.newConfidence = payload.confidence ?? 0;
    }
    streamFinishRef.current?.(payload.full_response, meta);
    if (payload.phase) {
      setCurrentPhase(payload.phase as DiagnosticPhase);
      setConfidence(payload.confidence ?? 0);
    }
  }, []);

  const handleChatPhaseUpdate = useCallback((phase: string, conf: number) => {
    setCurrentPhase(phase as DiagnosticPhase);
    setConfidence(conf);
  }, []);

  useWebSocketV4(sessionId ?? null, {
    onTaskEvent: handleTaskEvent,
    onChatResponse: handleChatResponse,
    onChatChunk: handleChatChunk,
    onChatStreamEnd: handleChatStreamEnd,
    onConnect: useCallback(() => { setWsConnected(true); setWsMaxReconnectsHit(false); }, []),
    onDisconnect: useCallback(() => setWsConnected(false), []),
    onMaxReconnectsExhausted: useCallback(() => {
      setWsMaxReconnectsHit(true);
      addToast('warning', 'Live connection lost — showing cached data');
    }, [addToast]),
  });

  const handleGoHome = useCallback(() => navigate('/'), [navigate]);
  const handleNavigateToDossier = useCallback(() => navigate(`/investigations/${sessionId}/dossier`), [navigate, sessionId]);

  const handleAttestationDecision = useCallback(
    (decision: string) => {
      if (sessionId && attestationGate) {
        submitAttestation(sessionId, attestationGate.gate_type, decision, 'user').catch((err) => {
          addToast('error', err instanceof Error ? err.message : 'Failed to submit attestation');
        });
      }
      setAttestationGate(null);
    },
    [sessionId, attestationGate, addToast],
  );

  // Loading state
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="material-symbols-outlined text-4xl text-slate-500 animate-spin">progress_activity</span>
      </div>
    );
  }

  // Error state
  if (error || !session) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-slate-300">
        <span className="material-symbols-outlined text-5xl text-slate-500">error_outline</span>
        <h2 className="text-lg font-display font-bold">Investigation not found</h2>
        <p className="text-sm text-slate-400">{error || 'This session does not exist or has expired.'}</p>
        <button
          onClick={() => navigate('/investigations')}
          className="px-4 py-2 rounded-lg bg-duck-accent/20 text-duck-accent text-sm font-medium hover:bg-duck-accent/30 transition-colors"
        >
          View all sessions
        </button>
      </div>
    );
  }

  // Render the correct war room based on capability
  const renderWarRoom = () => {
    if (session.capability === 'cluster_diagnostics') {
      return (
        <ChatProvider sessionId={sessionId ?? null} events={taskEvents} onRegisterChatHandler={chatResponseRef} onRegisterStreamStart={streamStartRef} onRegisterStreamAppend={streamAppendRef} onRegisterStreamFinish={streamFinishRef} onPhaseUpdate={handleChatPhaseUpdate}>
          <ClusterWarRoom
            session={session}
            events={taskEvents}
            wsConnected={wsConnected}
            phase={currentPhase}
            confidence={confidence}
            onGoHome={handleGoHome}
          />
        </ChatProvider>
      );
    }

    if (session.capability === 'network_troubleshooting') {
      return <NetworkWarRoom session={session} onGoHome={handleGoHome} />;
    }

    // Default: app diagnostics, database diagnostics, PR review, issue fix
    return (
      <ChatProvider sessionId={sessionId ?? null} events={taskEvents} onRegisterChatHandler={chatResponseRef} onRegisterStreamStart={streamStartRef} onRegisterStreamAppend={streamAppendRef} onRegisterStreamFinish={streamFinishRef} onPhaseUpdate={handleChatPhaseUpdate}>
        <CampaignProvider sessionId={sessionId ?? null}>
          <ForemanHUD
            sessionId={session.session_id}
            serviceName={session.service_name}
            phase={currentPhase}
            confidence={confidence}
            events={taskEvents}
            wsConnected={wsConnected}
            needsInput={false}
            onGoHome={handleGoHome}
            onOpenChat={() => {}}
          />
          {wsMaxReconnectsHit && (
            <div className="px-6 py-0">
              <ErrorBanner
                message="Live connection lost — showing cached data"
                severity="warning"
                onDismiss={() => setWsMaxReconnectsHit(false)}
                onRetry={() => window.location.reload()}
              />
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <ErrorBoundary>
              {session.capability === 'database_diagnostics' ? (
                <DatabaseWarRoom session={session} events={taskEvents} wsConnected={wsConnected} phase={currentPhase} confidence={confidence} />
              ) : (
                <InvestigationView
                  session={session}
                  events={taskEvents}
                  wsConnected={wsConnected}
                  phase={currentPhase}
                  confidence={confidence}
                  tokenUsage={tokenUsage}
                  attestationGate={attestationGate}
                  onAttestationDecision={handleAttestationDecision}
                  onNavigateToDossier={handleNavigateToDossier}
                />
              )}
            </ErrorBoundary>
          </div>
        </CampaignProvider>
      </ChatProvider>
    );
  };

  return renderWarRoom();
}
```

**Step 2: Create DossierRoute wrapper**

In the same file or as a separate export:

```tsx
export function DossierRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  if (!sessionId) return <NotFound />;

  return (
    <PostMortemDossierView
      sessionId={sessionId}
      onBack={() => navigate(`/investigations/${sessionId}`)}
    />
  );
}
```

Add import for `PostMortemDossierView` at the top:
```tsx
import PostMortemDossierView from '../components/Investigation/PostMortemDossierView';
```

**Step 3: Add investigation routes to router.tsx**

```tsx
import InvestigationRoute from './pages/InvestigationRoute';
import { DossierRoute } from './pages/InvestigationRoute';

// Add these routes inside the children array:
{ path: 'investigations/:sessionId', element: <InvestigationRoute /> },
{ path: 'investigations/:sessionId/dossier', element: <DossierRoute /> },
```

**Step 4: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/pages/InvestigationRoute.tsx src/router.tsx
git commit -m "feat(routing): add self-sufficient investigation + dossier routes"
```

---

### Task 13: Make SessionsRoute self-sufficient

The sessions list should fetch its own data instead of receiving `sessions` as props.

**Files:**
- Modify: `frontend/src/router.tsx`

**Step 1: Update SessionsRoute to fetch sessions**

```tsx
import { useQuery } from '@tanstack/react-query';
import { API_BASE_URL } from './services/api';

function SessionsRoute() {
  const navigate = useNavigate();

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/v4/sessions`);
      if (!response.ok) throw new Error('Failed to fetch sessions');
      return response.json();
    },
  });

  return (
    <SessionManagerView
      sessions={sessions}
      onSessionsChange={() => {}}
      onSelectSession={(session) => navigate(`/investigations/${session.session_id}`)}
    />
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 3: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/router.tsx
git commit -m "feat(routing): make SessionsRoute self-sufficient with data fetching"
```

---

## Phase 3: Migrate Network Section

### Task 14: Create NetworkLayout with sub-navigation

**Files:**
- Create: `frontend/src/layouts/NetworkLayout.tsx`
- Modify: `frontend/src/router.tsx`

**Step 1: Create NetworkLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const networkNav = [
  { to: '/network/topology', label: 'Topology', icon: 'device_hub' },
  { to: '/network/adapters', label: 'Adapters', icon: 'settings_input_component' },
  { to: '/network/monitoring', label: 'Devices', icon: 'router' },
  { to: '/network/ipam', label: 'IPAM', icon: 'dns' },
  { to: '/network/flows', label: 'Flows', icon: 'grid_view' },
  { to: '/network/observatory', label: 'Observatory', icon: 'monitoring' },
  { to: '/network/mib-browser', label: 'MIB Browser', icon: 'manage_search' },
  { to: '/network/cloud', label: 'Cloud', icon: 'cloud' },
  { to: '/network/security', label: 'Security', icon: 'security' },
];

export default function NetworkLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Sub-navigation tabs */}
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {networkNav.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? 'bg-duck-accent/10 text-duck-accent'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Route content */}
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
```

**Step 2: Update router.tsx to nest network routes under NetworkLayout**

Replace the flat network routes with:

```tsx
import NetworkLayout from './layouts/NetworkLayout';

// In the children array, replace individual network routes with:
{
  path: 'network',
  element: <NetworkLayout />,
  children: [
    { path: 'topology', element: <TopologyEditorView /> },
    { path: 'adapters', element: <NetworkAdaptersView /> },
    { path: 'monitoring', element: <DeviceMonitoring /> },
    { path: 'ipam', element: <IPAMDashboard /> },
    { path: 'flows', element: <ReachabilityMatrix /> },
    { path: 'observatory', element: <ObservatoryRoute /> },
    { path: 'mib-browser', element: <MIBBrowserView /> },
    { path: 'cloud', element: <CloudResourcesView /> },
    { path: 'security', element: <SecurityResourcesView /> },
  ],
},
// Keep live-topology outside NetworkLayout (it's full-screen)
{ path: 'network/live-topology', element: <LiveTopologyRoute /> },
```

**Step 3: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/NetworkLayout.tsx src/router.tsx
git commit -m "feat(routing): add NetworkLayout with sub-navigation tabs"
```

---

## Phase 4: Migrate Database Section

### Task 15: Create DatabaseLayout with sub-navigation

**Files:**
- Create: `frontend/src/layouts/DatabaseLayout.tsx`
- Modify: `frontend/src/router.tsx`

**Step 1: Create DatabaseLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const dbNav = [
  { to: '/database', label: 'Overview', icon: 'dashboard', end: true },
  { to: '/database/connections', label: 'Connections', icon: 'cable' },
  { to: '/database/diagnostics', label: 'Diagnostics', icon: 'troubleshoot' },
  { to: '/database/monitoring', label: 'Monitoring', icon: 'monitoring' },
  { to: '/database/schema', label: 'Schema', icon: 'account_tree' },
  { to: '/database/operations', label: 'Operations', icon: 'build' },
];

export default function DatabaseLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {dbNav.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? 'bg-duck-accent/10 text-duck-accent'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
```

**Step 2: Update router.tsx — nest database routes**

```tsx
import DatabaseLayout from './layouts/DatabaseLayout';

{
  path: 'database',
  element: <DatabaseLayout />,
  children: [
    { index: true, element: <DBOverview /> },
    { path: 'connections', element: <DBConnections /> },
    { path: 'diagnostics', element: <DBDiagnosticsPage /> },
    { path: 'monitoring', element: <DBMonitoring /> },
    { path: 'schema', element: <DBSchema /> },
    { path: 'operations', element: <DBOperations /> },
  ],
},
```

**Step 3: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/DatabaseLayout.tsx src/router.tsx
git commit -m "feat(routing): add DatabaseLayout with sub-navigation tabs"
```

---

## Phase 5: Migrate Remaining Sections

### Task 16: Create ClustersLayout, AgentsLayout, WorkflowsLayout, SettingsLayout

**Files:**
- Create: `frontend/src/layouts/ClustersLayout.tsx`
- Create: `frontend/src/layouts/AgentsLayout.tsx`
- Create: `frontend/src/layouts/WorkflowsLayout.tsx`
- Create: `frontend/src/layouts/SettingsLayout.tsx`
- Modify: `frontend/src/router.tsx`

**Step 1: Create ClustersLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const clustersNav = [
  { to: '/clusters', label: 'Clusters', icon: 'deployed_code', end: true },
  { to: '/clusters/registry', label: 'Fleet', icon: 'cloud_circle' },
  { to: '/clusters/recommendations', label: 'Recommendations', icon: 'tips_and_updates' },
];

export default function ClustersLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {clustersNav.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive ? 'bg-duck-accent/10 text-duck-accent' : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden"><Outlet /></div>
    </div>
  );
}
```

**Step 2: Create AgentsLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const agentsNav = [
  { to: '/agents', label: 'Catalog', icon: 'smart_toy', end: true },
  { to: '/agents/matrix', label: 'Matrix', icon: 'grid_view' },
];

export default function AgentsLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {agentsNav.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive ? 'bg-duck-accent/10 text-duck-accent' : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden"><Outlet /></div>
    </div>
  );
}
```

**Step 3: Create WorkflowsLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const workflowsNav = [
  { to: '/workflows', label: 'Builder', icon: 'account_tree', end: true },
  { to: '/workflows/runs', label: 'Runs', icon: 'play_circle' },
];

export default function WorkflowsLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {workflowsNav.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive ? 'bg-duck-accent/10 text-duck-accent' : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden"><Outlet /></div>
    </div>
  );
}
```

**Step 4: Create SettingsLayout**

```tsx
import { NavLink, Outlet } from 'react-router-dom';

const settingsNav = [
  { to: '/settings', label: 'Settings', icon: 'settings', end: true },
  { to: '/settings/integrations', label: 'Integrations', icon: 'hub' },
];

export default function SettingsLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {settingsNav.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive ? 'bg-duck-accent/10 text-duck-accent' : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden"><Outlet /></div>
    </div>
  );
}
```

**Step 5: Update router.tsx — nest all remaining sections**

```tsx
import ClustersLayout from './layouts/ClustersLayout';
import AgentsLayout from './layouts/AgentsLayout';
import WorkflowsLayout from './layouts/WorkflowsLayout';
import SettingsLayout from './layouts/SettingsLayout';

// Replace flat routes with nested:
{
  path: 'clusters',
  element: <ClustersLayout />,
  children: [
    { index: true, element: <KubernetesClusters /> },
    { path: 'registry', element: <ClusterRegistryRoute /> },
    { path: 'recommendations', element: <ClusterRecommendationsRoute /> },
  ],
},
{
  path: 'agents',
  element: <AgentsLayout />,
  children: [
    { index: true, element: <AgentCatalogView /> },
    { path: 'matrix', element: <AgentMatrixRoute /> },
  ],
},
{
  path: 'workflows',
  element: <WorkflowsLayout />,
  children: [
    { index: true, element: <WorkflowBuilderView /> },
    { path: 'runs', element: <WorkflowRunsRoute /> },
  ],
},
{
  path: 'settings',
  element: <SettingsLayout />,
  children: [
    { index: true, element: <SettingsView /> },
    { path: 'integrations', element: <IntegrationsRoute /> },
  ],
},
```

**Step 6: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/layouts/ClustersLayout.tsx src/layouts/AgentsLayout.tsx src/layouts/WorkflowsLayout.tsx src/layouts/SettingsLayout.tsx src/router.tsx
git commit -m "feat(routing): add section layouts with sub-navigation for clusters, agents, workflows, settings"
```

---

## Phase 6: Cleanup

### Task 17: Replace API_BASE_URL with relative paths

The `api.ts` currently hardcodes `http://localhost:8000`. Since Vite proxies `/api` and `/ws`, we can use relative paths. This makes the app work correctly in production too.

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Replace API_BASE_URL**

Change:
```tsx
export const API_BASE_URL = 'http://localhost:8000';
```

To:
```tsx
export const API_BASE_URL = '';
```

This makes all `fetch(`${API_BASE_URL}/api/...`)` calls use relative URLs like `/api/...`, which Vite proxies in dev and the production server handles directly.

**Step 2: Check for other hardcoded localhost references**

Run: `grep -r "localhost:8000" frontend/src/ --include="*.ts" --include="*.tsx"`
Fix any remaining hardcoded URLs to use relative paths or `API_BASE_URL`.

**Step 3: Verify dev server still works**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx vite --host 0.0.0.0 &`
Verify API calls work (check network tab in browser).
Kill dev server.

**Step 4: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add src/services/api.ts
git commit -m "fix(api): replace hardcoded localhost with relative paths for production"
```

---

### Task 18: Remove old view switching logic from App.tsx

Now that all routes are handled by the router, the old `App.tsx` with its `ViewState` type, `handleNavigate`, and 35+ conditional renders can be cleaned up. Keep `App.tsx` as a minimal shell or remove it entirely if `main.tsx` now renders `RouterProvider` directly.

**Files:**
- Modify: `frontend/src/App.tsx` (reduce to re-export or delete)

**Step 1: Reduce App.tsx**

Since `main.tsx` now renders `<RouterProvider>` directly with `QueryClientProvider` and `ToastProvider`, `App.tsx` is no longer the entry point. Either:

a) Delete `App.tsx` entirely if nothing imports it.
b) Or keep it as a minimal re-export if other files import `App`.

Check for imports:
```bash
grep -r "from.*App" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".test."
```

If only `main.tsx` imports it and `main.tsx` has been updated, delete `App.tsx`.

**Step 2: Remove unused NavView/ViewState types if no longer referenced**

Check if `NavView` is still used:
```bash
grep -r "NavView" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v node_modules
```

`NavView` is still used by `SidebarNav.tsx` and `NavigationContext.tsx`, so keep it.

Check if `ViewState` is used anywhere besides `App.tsx`:
```bash
grep -r "ViewState" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v node_modules
```

If only in `App.tsx`, it gets removed with the file.

**Step 3: Verify it compiles**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit --pretty`

**Step 4: Verify the full app works end-to-end**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx vite --host 0.0.0.0 &`
- Dashboard loads at `/`
- Sidebar navigation works (URL changes, views switch)
- Browser back/forward works
- Direct URL access works (e.g. `/network/topology`)
- 404 page works for invalid URLs
- Settings, audit, agents, workflows sections work
Kill dev server.

**Step 5: Verify production build**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npm run build`
Expected: Build succeeds with no errors.

**Step 6: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend
git add -A
git commit -m "refactor(routing): remove old ViewState-based navigation from App.tsx"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `npm run build` succeeds (TypeScript + Vite)
- [ ] All 35+ views accessible via URL paths
- [ ] Browser back/forward works correctly
- [ ] Direct URL access works (deep linking)
- [ ] Sidebar highlights correct item based on URL
- [ ] 404 page shows for invalid routes
- [ ] Investigation routes load session from URL params
- [ ] Dossier route loads from URL params
- [ ] Capability form accessible via `/investigations/new?capability=...`
- [ ] Section sub-navigation tabs work (Network, Database, Clusters, etc.)
- [ ] WebSocket reconnects when navigating to active investigation
- [ ] API calls use relative paths (no hardcoded localhost)
