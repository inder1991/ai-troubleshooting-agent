import type { ClusterDomainKey } from '../../types';

export const DOMAIN_META: Record<ClusterDomainKey, { icon: string; label: string; color: string }> = {
  ctrl_plane: { icon: 'settings_system_daydream', label: 'CONTROL PLANE', color: '#f59e0b' },
  node: { icon: 'memory', label: 'COMPUTE', color: '#13b6ec' },
  network: { icon: 'network_check', label: 'NETWORK', color: '#10b981' },
  storage: { icon: 'database', label: 'STORAGE', color: '#8b5cf6' },
};
