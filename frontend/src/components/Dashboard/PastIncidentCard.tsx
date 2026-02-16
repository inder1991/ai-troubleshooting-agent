import React from 'react';
import { History, CheckCircle, Clock, AlertTriangle, Server } from 'lucide-react';
import type { PastIncidentMatch } from '../../types';

interface PastIncidentCardProps {
  incidents: PastIncidentMatch[];
}

const PastIncidentCard: React.FC<PastIncidentCardProps> = ({ incidents }) => {
  if (incidents.length === 0) return null;

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-4 flex items-center gap-1.5">
        <History className="w-3.5 h-3.5 text-[#07b6d5]" />
        Past Incident Matches
      </h4>
      {incidents.map((incident, idx) => (
        <div
          key={incident.fingerprint_id || idx}
          className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-3 space-y-2"
        >
          {/* Header: similarity score */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-[#07b6d5]/20 flex items-center justify-center">
                <History className="w-3 h-3 text-[#07b6d5]" />
              </div>
              <span className="text-xs text-gray-400 font-mono">
                Session {incident.session_id.slice(0, 8)}...
              </span>
            </div>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                incident.similarity_score >= 0.8
                  ? 'bg-green-500/20 text-green-400'
                  : incident.similarity_score >= 0.6
                  ? 'bg-yellow-500/20 text-yellow-400'
                  : 'bg-blue-500/20 text-blue-400'
              }`}
            >
              {Math.round(incident.similarity_score * 100)}% match
            </span>
          </div>

          {/* Root cause */}
          {incident.root_cause && (
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-3 h-3 text-orange-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-gray-300">{incident.root_cause}</p>
            </div>
          )}

          {/* Affected services */}
          {incident.affected_services.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Server className="w-3 h-3 text-blue-400 flex-shrink-0" />
              {incident.affected_services.map((svc, i) => (
                <span
                  key={i}
                  className="text-xs bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded"
                >
                  {svc}
                </span>
              ))}
            </div>
          )}

          {/* Error patterns */}
          {incident.error_patterns.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <AlertTriangle className="w-3 h-3 text-red-400 flex-shrink-0" />
              {incident.error_patterns.slice(0, 3).map((ep, i) => (
                <span
                  key={i}
                  className="text-xs bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded font-mono"
                >
                  {ep}
                </span>
              ))}
            </div>
          )}

          {/* Resolution steps */}
          {incident.resolution_steps.length > 0 && (
            <div className="space-y-1 mt-1">
              <span className="text-xs text-gray-500 font-semibold">Resolution steps:</span>
              {incident.resolution_steps.map((step, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <CheckCircle className="w-3 h-3 text-green-400 mt-0.5 flex-shrink-0" />
                  <span className="text-xs text-gray-400">{step}</span>
                </div>
              ))}
            </div>
          )}

          {/* Time to resolve + action */}
          <div className="flex items-center justify-between pt-1 border-t border-[#224349]">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3 text-gray-500" />
              <span className="text-xs text-gray-500">
                Resolved in {formatDuration(incident.time_to_resolve)}
              </span>
            </div>
            <button className="text-xs bg-[#07b6d5]/20 text-[#07b6d5] px-2 py-1 rounded hover:bg-[#07b6d5]/30 transition-colors">
              Apply Same Resolution
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default PastIncidentCard;
