import { createBrowserRouter, useNavigate, useSearchParams } from 'react-router-dom';
import AppLayout from './layouts/AppLayout';
import NotFound from './pages/NotFound';
import InvestigationRoute, { DossierRoute } from './pages/InvestigationRoute';
import type { CapabilityType, CapabilityFormData } from './types';
import { startSessionV4 } from './services/api';
import CapabilityForm from './components/ActionCenter/CapabilityForm';

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
 * Route wrapper components that adapt existing components to work as route elements.
 * Each wrapper uses useNavigate() to wire navigation callbacks.
 */

function HomeRoute() {
  const navigate = useNavigate();
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
  return <WorkflowRunsView onNavigate={() => navigate('/workflows')} />;
}

function CapabilityFormRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const capability = searchParams.get('capability') as CapabilityType | null;

  if (!capability) {
    return <NotFound />;
  }

  const handleSubmit = async (data: CapabilityFormData) => {
    try {
      const session = await startSessionV4({
        service_name: (data as any).service_name || capability,
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

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomeRoute /> },
      { path: 'how-it-works', element: <HowItWorksRoute /> },

      // Investigations
      { path: 'investigations', element: <SessionsRoute /> },
      { path: 'investigations/new', element: <CapabilityFormRoute /> },
      { path: 'investigations/:sessionId', element: <InvestigationRoute /> },
      { path: 'investigations/:sessionId/dossier', element: <DossierRoute /> },

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
      { path: 'clusters/registry', element: <ClusterRegistryRoute /> },
      { path: 'clusters/recommendations', element: <ClusterRecommendationsRoute /> },

      // Agents section
      { path: 'agents', element: <AgentCatalogView /> },
      { path: 'agents/matrix', element: <AgentMatrixRoute /> },

      // Workflows section
      { path: 'workflows', element: <WorkflowBuilderView /> },
      { path: 'workflows/runs', element: <WorkflowRunsRoute /> },

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
