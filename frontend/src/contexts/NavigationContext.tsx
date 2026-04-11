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
  cicd: '/cicd',
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
