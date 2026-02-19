import React from 'react';
import { Shield, ArrowUpRight, ArrowDownRight, Database, Users, Target, Briefcase } from 'lucide-react';
import type { BlastRadiusData, SeverityData } from '../../types';

interface ImpactCardProps {
  blastRadius: BlastRadiusData | null;
  severity: SeverityData | null;
}

const severityConfig: Record<string, { bg: string; text: string; border: string; glow: string }> = {
  P1: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50', glow: 'shadow-red-500/20' },
  P2: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/50', glow: 'shadow-orange-500/20' },
  P3: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/50', glow: 'shadow-yellow-500/20' },
  P4: { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/50', glow: 'shadow-green-500/20' },
};

const riskConfig: Record<string, { bg: string; text: string }> = {
  critical: { bg: 'bg-red-500/20', text: 'text-red-400' },
  high: { bg: 'bg-orange-500/20', text: 'text-orange-400' },
  medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-400' },
  low: { bg: 'bg-green-500/20', text: 'text-green-400' },
};

const scopeLabels: Record<string, string> = {
  single_service: 'Single Service',
  service_group: 'Service Group',
  namespace: 'Namespace',
  cluster_wide: 'Cluster Wide',
};

const ImpactCard: React.FC<ImpactCardProps> = ({ blastRadius, severity }) => {
  if (!blastRadius || !severity) return null;

  const config = severityConfig[severity.recommended_severity] || severityConfig.P3;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-4 flex items-center gap-1.5">
        <Shield className="w-3.5 h-3.5 text-[#07b6d5]" />
        Impact Analysis
      </h4>

      <div className="bg-[#1e2f33]/50 border border-[#224349] rounded-lg p-4">
        {/* Severity Badge */}
        <div className="flex items-center justify-between mb-4">
          <div
            className={`px-4 py-2 rounded-lg ${config.bg} ${config.border} border shadow-lg ${config.glow}`}
          >
            <span className={`text-2xl font-bold ${config.text}`}>
              {severity.recommended_severity}
            </span>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-400">Blast Radius</div>
            <div className="text-sm font-medium text-white">
              {scopeLabels[blastRadius.scope] || blastRadius.scope}
            </div>
          </div>
        </div>

        {/* Reasoning */}
        <p className="text-xs text-gray-400 mb-4 italic">{severity.reasoning}</p>

        {/* Primary Service */}
        <div className="flex items-center justify-center mb-4">
          <div className="flex items-center gap-2 bg-[#07b6d5]/10 border border-[#07b6d5]/30 rounded-lg px-3 py-2">
            <Target className="w-4 h-4 text-[#07b6d5]" />
            <span className="text-sm font-medium text-[#07b6d5]">
              {blastRadius.primary_service}
            </span>
          </div>
        </div>

        {/* Upstream / Downstream */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          {/* Upstream */}
          <div>
            <div className="flex items-center gap-1 mb-1.5">
              <ArrowUpRight className="w-3 h-3 text-orange-400" />
              <span className="text-xs text-gray-400">Upstream ({blastRadius.upstream_affected.length})</span>
            </div>
            <div className="space-y-1">
              {blastRadius.upstream_affected.length > 0 ? (
                blastRadius.upstream_affected.map((svc) => (
                  <div
                    key={svc}
                    className="text-xs text-gray-300 bg-[#0d1b1e] rounded px-2 py-1 truncate"
                  >
                    {svc}
                  </div>
                ))
              ) : (
                <span className="text-xs text-gray-600">None</span>
              )}
            </div>
          </div>

          {/* Downstream */}
          <div>
            <div className="flex items-center gap-1 mb-1.5">
              <ArrowDownRight className="w-3 h-3 text-blue-400" />
              <span className="text-xs text-gray-400">Downstream ({blastRadius.downstream_affected.length})</span>
            </div>
            <div className="space-y-1">
              {blastRadius.downstream_affected.length > 0 ? (
                blastRadius.downstream_affected.map((svc) => (
                  <div
                    key={svc}
                    className="text-xs text-gray-300 bg-[#0d1b1e] rounded px-2 py-1 truncate"
                  >
                    {svc}
                  </div>
                ))
              ) : (
                <span className="text-xs text-gray-600">None</span>
              )}
            </div>
          </div>
        </div>

        {/* Shared Resources */}
        {blastRadius.shared_resources.length > 0 && (
          <div className="mb-3">
            <div className="flex items-center gap-1 mb-1.5">
              <Database className="w-3 h-3 text-purple-400" />
              <span className="text-xs text-gray-400">
                Shared Resources ({blastRadius.shared_resources.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {blastRadius.shared_resources.map((res) => (
                <span
                  key={res}
                  className="text-xs text-purple-300 bg-purple-500/10 border border-purple-500/20 rounded px-2 py-0.5"
                >
                  {res}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* User Impact */}
        <div className="flex items-center gap-2 pt-2 border-t border-[#224349]">
          <Users className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-xs text-gray-300">
            {blastRadius.estimated_user_impact}
          </span>
        </div>

        {/* Business Impact */}
        {blastRadius.business_impact && blastRadius.business_impact.length > 0 && (
          <div className="mt-3 pt-2 border-t border-[#224349]">
            <div className="flex items-center gap-1 mb-2">
              <Briefcase className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
                Business Impact
              </span>
            </div>
            <div className="space-y-1.5">
              {blastRadius.business_impact.map((cap) => (
                <div key={cap.capability} className="flex items-center justify-between">
                  <span className="text-xs text-gray-300">{cap.capability}</span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                    riskConfig[cap.risk_level]?.bg || 'bg-gray-500/20'
                  } ${riskConfig[cap.risk_level]?.text || 'text-gray-400'}`}>
                    {cap.risk_level === 'critical' ? 'At Risk' :
                     cap.risk_level === 'high' ? 'Degraded' :
                     cap.risk_level === 'medium' ? 'Monitoring' : 'Stable'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Factors */}
        {Object.keys(severity.factors).length > 0 && (
          <div className="mt-3 pt-2 border-t border-[#224349]">
            <div className="flex flex-wrap gap-2">
              {Object.entries(severity.factors).map(([key, value]) => (
                <span
                  key={key}
                  className="text-xs text-gray-500 bg-[#0d1b1e] rounded px-2 py-0.5"
                >
                  {key}: {value}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ImpactCard;
