export type Environment = 'prod' | 'staging' | 'dev';
export type ProfileStatus = 'connected' | 'warning' | 'unreachable' | 'pending_setup';
export type EndpointStatus = 'unknown' | 'healthy' | 'testing' | 'degraded' | 'unreachable' | 'connection_failed';
export type GlobalIntegrationStatus = 'connected' | 'not_validated' | 'not_linked' | 'conn_error';

export interface EndpointConfig {
  url: string;
  auth_method: string;
  has_credentials: boolean;
  verified: boolean;
  last_verified: string | null;
  status: EndpointStatus;
}

export interface ClusterEndpoints {
  openshift_api: EndpointConfig | null;
  prometheus: EndpointConfig | null;
  jaeger: EndpointConfig | null;
}

export interface ClusterProfile {
  id: string;
  name: string;
  display_name: string | null;
  cluster_type: 'openshift' | 'kubernetes';
  cluster_url: string;
  environment: Environment;
  auth_method: 'kubeconfig' | 'token' | 'service_account' | 'none';
  has_cluster_credentials: boolean;
  endpoints: ClusterEndpoints;
  created_at: string;
  updated_at: string;
  last_synced: string | null;
  status: ProfileStatus;
  cluster_version: string | null;
  is_active: boolean;
}

export interface GlobalIntegration {
  id: string;
  service_type: 'elk' | 'jira' | 'confluence' | 'remedy' | 'github';
  name: string;
  category: string;
  url: string;
  auth_method: string;
  has_credentials: boolean;
  config?: Record<string, unknown>;
  status: GlobalIntegrationStatus;
  last_verified: string | null;
}

export interface EndpointTestResult {
  name: string;
  reachable: boolean;
  discovered_url: string | null;
  latency_ms: number | null;
  error: string | null;
}
