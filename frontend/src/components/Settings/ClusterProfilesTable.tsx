import React from 'react';
import type { ClusterProfile, Environment, ProfileStatus } from '../../types/profiles';

interface ClusterProfilesTableProps {
  profiles: ClusterProfile[];
  onEdit: (profile: ClusterProfile) => void;
  onDelete: (id: string) => void;
  onActivate: (id: string) => void;
  onAddNew: () => void;
}

const envBadge: Record<Environment, string> = {
  prod: 'bg-red-900/30 text-red-400 border border-red-500/20',
  staging: 'bg-[#07b6d5]/10 text-[#07b6d5] border border-[#07b6d5]/20',
  dev: 'bg-emerald-900/30 text-emerald-400 border border-emerald-500/20',
};

const statusDot: Record<ProfileStatus, { color: string; glow: string; label: string }> = {
  connected: { color: 'bg-green-500', glow: 'shadow-[0_0_8px_rgba(34,197,94,0.6)]', label: 'Connected' },
  warning: { color: 'bg-amber-500', glow: 'shadow-[0_0_8px_rgba(245,158,11,0.6)]', label: 'Warning' },
  unreachable: { color: 'bg-red-500', glow: 'shadow-[0_0_8px_rgba(239,68,68,0.6)]', label: 'Unreachable' },
  pending_setup: { color: 'bg-gray-500', glow: '', label: 'Pending Setup' },
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
}) => {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-white uppercase tracking-wider">
          Integrated Cluster Profiles
        </h2>
        <button
          onClick={onAddNew}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1e2f33] text-white border border-[#07b6d5]/20 rounded-lg text-xs font-medium hover:bg-[#1e2f33]/80 transition-colors"
        >
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            add
          </span>
          Add New Cluster
        </button>
      </div>

      {profiles.length === 0 ? (
        <div className="text-center text-gray-600 text-xs py-10 border border-dashed border-[#224349] rounded-xl">
          No cluster profiles configured. Add one to get started.
        </div>
      ) : (
        <div className="border border-[#224349] rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[#1e2f33]/50 text-gray-500 uppercase tracking-wider">
                <th className="text-left px-4 py-2.5 font-medium">Profile Name</th>
                <th className="text-left px-4 py-2.5 font-medium">Environment</th>
                <th className="text-left px-4 py-2.5 font-medium">Cluster Type</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-left px-4 py-2.5 font-medium">Last Synced</th>
                <th className="text-right px-4 py-2.5 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#224349]/50">
              {profiles.map((profile) => {
                const status = statusDot[profile.status];
                return (
                  <tr
                    key={profile.id}
                    className="bg-[#0a1a1d] hover:bg-[#0a1a1d]/80 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {profile.is_active && (
                          <span className="w-1.5 h-1.5 rounded-full bg-[#07b6d5] shadow-[0_0_6px_rgba(7,182,213,0.6)]" />
                        )}
                        <span className="font-semibold text-white">{profile.name}</span>
                      </div>
                      <span className="text-[10px] text-gray-600 font-mono block mt-0.5">
                        {profile.cluster_url}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase ${envBadge[profile.environment]}`}
                      >
                        {profile.environment}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {profile.cluster_type === 'openshift' ? 'OpenShift' : 'Kubernetes'}
                      {profile.cluster_version && (
                        <span className="text-gray-600 ml-1">{profile.cluster_version}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full ${status.color} ${status.glow}`}
                        />
                        <span className="text-gray-400">{status.label}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 italic">
                      {timeAgo(profile.last_synced)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {!profile.is_active && (
                          <button
                            onClick={() => onActivate(profile.id)}
                            className="p-1.5 text-gray-500 hover:text-[#07b6d5] hover:bg-[#1e2f33] rounded transition-colors"
                            title="Set as active"
                          >
                            <span
                              className="material-symbols-outlined text-sm"
                              style={{ fontFamily: 'Material Symbols Outlined' }}
                            >
                              check_circle
                            </span>
                          </button>
                        )}
                        <button
                          onClick={() => onEdit(profile)}
                          className="p-1.5 text-gray-500 hover:text-white hover:bg-[#1e2f33] rounded transition-colors"
                          title="Edit"
                        >
                          <span
                            className="material-symbols-outlined text-sm"
                            style={{ fontFamily: 'Material Symbols Outlined' }}
                          >
                            edit
                          </span>
                        </button>
                        <button
                          onClick={() => onDelete(profile.id)}
                          className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-[#1e2f33] rounded transition-colors"
                          title="Delete"
                        >
                          <span
                            className="material-symbols-outlined text-sm"
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
    </div>
  );
};

export default ClusterProfilesTable;
