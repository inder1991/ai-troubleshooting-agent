import type { ClusterDomainKey } from '../../types';

export const DOMAIN_META: Record<ClusterDomainKey, { icon: string; label: string; color: string }> = {
  ctrl_plane: { icon: 'settings_system_daydream', label: 'CONTROL PLANE', color: 'var(--wr-domain-ctrl-plane)' },
  node: { icon: 'memory', label: 'COMPUTE', color: 'var(--wr-domain-node)' },
  network: { icon: 'network_check', label: 'NETWORK', color: 'var(--wr-domain-network)' },
  storage: { icon: 'database', label: 'STORAGE', color: 'var(--wr-domain-storage)' },
  rbac: { icon: 'admin_panel_settings', label: 'RBAC', color: 'var(--wr-domain-rbac)' },
};
