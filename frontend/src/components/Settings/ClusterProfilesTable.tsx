import React from 'react';
import type { ClusterProfile, Environment, ProfileStatus } from '../../types/profiles';

interface ClusterProfilesTableProps {
  profiles: ClusterProfile[];
  onEdit: (profile: ClusterProfile) => void;
  onDelete: (id: string) => void;
  onActivate: (id: string) => void;
  onAddNew: () => void;
  onProbe?: (id: string) => Promise<void>;
  probingId?: string | null;
}

const envBadge: Record<Environment, string> = {
  prod: 'bg-red-900/30 text-red-400 border border-red-500/20',
  staging: 'bg-[#07b6d5]/10 text-[#07b6d5] border border-[#07b6d5]/20',
  dev: 'bg-emerald-900/30 text-emerald-400 border border-emerald-500/20',
};

const statusDot: Record<ProfileStatus, { color: string; glow: string; label: string; textColor: string }> = {
  connected: { color: 'bg-green-500', glow: 'shadow-[0_0_8px_rgba(34,197,94,0.6)]', label: 'Connected', textColor: 'text-green-500' },
  warning: { color: 'bg-amber-500', glow: 'shadow-[0_0_8px_rgba(245,158,11,0.6)]', label: 'Warning', textColor: 'text-amber-500' },
  unreachable: { color: 'bg-red-500', glow: 'shadow-[0_0_8px_rgba(239,68,68,0.6)]', label: 'Unreachable', textColor: 'text-red-500' },
  pending_setup: { color: 'bg-gray-500', glow: '', label: 'Pending Setup', textColor: 'text-gray-500' },
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const ClusterProfilesTable: React.FC<ClusterProfilesTableProps> = ({
  profiles,
  onEdit,
  onDelete,
  onActivate,
  onAddNew,
  onProbe,
  probingId,
}) => {
  return (
    <section>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">Integrated Cluster Profiles</h3>
          <p className="text-[#8fc3cc] text-sm">Active observability pipelines and cluster endpoints.</p>
        </div>
        <button
          onClick={onAddNew}
          className="flex items-center gap-2 bg-[#224349] text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-[#224349]/80 transition-colors border border-[#07b6d5]/20"
        >
          <span
            className="material-symbols-outlined text-[18px]"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            add_circle
          </span>
          Add New Cluster
        </button>
      </div>

      {profiles.length === 0 ? (
        <div className="text-center text-gray-600 text-xs py-10 bg-[#183034]/30 border border-dashed border-[#224349] rounded-xl">
          No cluster profiles configured. Add one to get started.
        </div>
      ) : (
        <div className="bg-[#183034]/30 rounded-xl border border-[#224349] overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[#183034]/50 border-b border-[#224349]">
              <tr>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider">Profile Name</th>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider">Environment</th>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider">Cluster Type</th>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider">Last Synced</th>
                <th className="px-6 py-3 text-xs font-bold text-[#8fc3cc] uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#224349]">
              {profiles.map((profile) => {
                const status = statusDot[profile.status];
                return (
                  <tr
                    key={profile.id}
                    className="hover:bg-[#183034]/20 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {profile.is_active && (
                          <span className="w-1.5 h-1.5 rounded-full bg-[#07b6d5] shadow-[0_0_6px_rgba(7,182,213,0.6)]" />
                        )}
                        <span className="text-sm font-medium text-white">{profile.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span
                        className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-tighter ${envBadge[profile.environment]}`}
                      >
                        {profile.environment}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#8fc3cc]">
                      {profile.cluster_type === 'openshift' ? 'OpenShift' : 'Kubernetes'}
                      {profile.cluster_version && (
                        <span className="ml-1">{profile.cluster_version}</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full ${status.color} ${status.glow}`}
                        />
                        <span className={`text-xs font-medium ${status.textColor}`}>{status.label}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs text-[#8fc3cc] italic">
                      {timeAgo(profile.last_synced)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {!profile.is_active && (
                          <button
                            onClick={() => onActivate(profile.id)}
                            className="p-1.5 hover:bg-[#07b6d5]/20 text-[#8fc3cc] hover:text-[#07b6d5] rounded transition-colors"
                            title="Set as active"
                          >
                            <span
                              className="material-symbols-outlined text-[18px]"
                              style={{ fontFamily: 'Material Symbols Outlined' }}
                            >
                              check_circle
                            </span>
                          </button>
                        )}
                        {onProbe && (
                          <button
                            onClick={() => onProbe(profile.id)}
                            disabled={probingId === profile.id}
                            className="p-1.5 hover:bg-[#07b6d5]/20 text-[#8fc3cc] hover:text-[#07b6d5] rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Probe / Auto-discover"
                          >
                            <span
                              className={`material-symbols-outlined text-[18px] ${probingId === profile.id ? 'animate-spin' : ''}`}
                              style={{ fontFamily: 'Material Symbols Outlined' }}
                            >
                              radar
                            </span>
                          </button>
                        )}
                        <button
                          onClick={() => onEdit(profile)}
                          className="p-1.5 hover:bg-[#07b6d5]/20 text-[#8fc3cc] hover:text-[#07b6d5] rounded transition-colors"
                          title="Edit"
                        >
                          <span
                            className="material-symbols-outlined text-[18px]"
                            style={{ fontFamily: 'Material Symbols Outlined' }}
                          >
                            edit
                          </span>
                        </button>
                        <button
                          onClick={() => onDelete(profile.id)}
                          className="p-1.5 hover:bg-red-500/20 text-[#8fc3cc] hover:text-red-400 rounded transition-colors"
                          title="Delete"
                        >
                          <span
                            className="material-symbols-outlined text-[18px]"
                            style={{ fontFamily: 'Material Symbols Outlined' }}
                          >
                            delete
                          </span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default ClusterProfilesTable;
