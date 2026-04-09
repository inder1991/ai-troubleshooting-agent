import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './layouts/AppLayout';
import NotFound from './pages/NotFound';

// Existing page components
import HomePage from './components/Home/HomePage';
import HowItWorksView from './components/HowItWorks/HowItWorksView';
import SessionManagerView from './components/Sessions/SessionManagerView';
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
 * Temporary wrapper components that adapt existing components to work as route elements.
 * These pass stub callbacks — Task 9 will wire them with useNavigate().
 */

function HomeRoute() {
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

      // Investigations
      { path: 'investigations', element: <SessionsRoute /> },

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
