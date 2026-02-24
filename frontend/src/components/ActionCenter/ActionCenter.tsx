import React from 'react';
import { Search, FileText, Bug, Container, Activity } from 'lucide-react';
import type { CapabilityType, V4Session } from '../../types';
import CapabilityCard from './CapabilityCard';

interface ActionCenterProps {
  onSelectCapability: (capability: CapabilityType) => void;
  sessions: V4Session[];
  onSelectSession: (session: V4Session) => void;
}

const capabilities: {
  type: CapabilityType;
  title: string;
  description: string;
  icon: typeof Search;
  color: string;
}[] = [
  {
    type: 'troubleshoot_app',
    title: 'Troubleshoot',
    description: 'Scan logs and metrics for anomalies across microservices',
    icon: Search,
    color: '#07b6d5',
  },
  {
    type: 'pr_review',
    title: 'PR Review',
    description: 'Automated code quality & security for active pull requests',
    icon: FileText,
    color: '#a78bfa',
  },
  {
    type: 'github_issue_fix',
    title: 'Issue Fixer',
    description: 'Generate and apply automated patches to known vulnerabilities',
    icon: Bug,
    color: '#f97316',
  },
  {
    type: 'cluster_diagnostics',
    title: 'Cluster Diag',
    description: 'Full-stack health check of OpenShift/K8s cluster and node status',
    icon: Container,
    color: '#14b8a6',
  },
];

const ActionCenter: React.FC<ActionCenterProps> = ({
  onSelectCapability,
  sessions,
  onSelectSession,
}) => {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white mb-1">Capability Launcher</h1>
          <p className="text-sm text-gray-400">
            Deploy automated diagnostics and remediations
          </p>
        </div>

        {/* Capability Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-10">
          {capabilities.map((cap) => (
            <CapabilityCard
              key={cap.type}
              capability={cap.type}
              title={cap.title}
              description={cap.description}
              icon={cap.icon}
              color={cap.color}
              onSelect={onSelectCapability}
            />
          ))}
        </div>

        {/* Live Intelligence Feed */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-[#07b6d5]" />
            <h2 className="text-sm font-semibold text-white">Live Intelligence Feed</h2>
            <span className="text-xs text-gray-500">
              {sessions.length} session{sessions.length !== 1 ? 's' : ''}
            </span>
          </div>

          {sessions.length === 0 ? (
            <div className="bg-[#1e2f33]/30 border border-[#224349] rounded-xl p-8 text-center">
              <p className="text-gray-500 text-sm">No active sessions. Launch a capability to begin.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.slice(0, 8).map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => onSelectSession(session)}
                  className="w-full text-left bg-[#1e2f33]/30 border border-[#224349] rounded-lg p-3 hover:border-[#07b6d5]/30 transition-colors group"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-[#07b6d5] animate-pulse" />
                      <span className="text-sm text-white font-medium">
                        {session.service_name}
                      </span>
                      <span className="text-xs text-gray-500 font-mono">
                        {session.session_id.substring(0, 8)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-400 capitalize">
                        {session.status.replace(/_/g, ' ')}
                      </span>
                      {session.confidence > 0 && (
                        <span className="text-xs text-[#07b6d5] font-mono">
                          {Math.round(session.confidence)}%
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ActionCenter;
