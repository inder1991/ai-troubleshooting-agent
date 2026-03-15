import React, { useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getClusterRecommendations, refreshClusterRecommendations } from '../../services/api';
import type { ScoredRecommendationDTO } from '../../types';
import RecommendationCard from './RecommendationCard';
import CostBreakdownPanel from './CostBreakdownPanel';

interface ClusterRecommendationsPageProps {
  clusterId: string;
  onBack: () => void;
}

const sectionConfig = [
  { key: 'critical', label: 'Critical Risks', borderColor: '#ef4444', categories: ['reliability', 'stability'], severities: ['critical', 'high'] },
  { key: 'optimization', label: 'Workload Optimization', borderColor: '#e09f3e', categories: ['cost', 'rightsizing', 'efficiency'], severities: null },
  { key: 'security', label: 'Security & Compliance', borderColor: '#eab308', categories: ['security', 'compliance'], severities: null },
  { key: 'known', label: 'Known Issues', borderColor: '#6b7280', categories: null, severities: null },
];

const ClusterRecommendationsPage: React.FC<ClusterRecommendationsPageProps> = ({ clusterId, onBack }) => {
  const queryClient = useQueryClient();

  const { data: snapshot, isLoading, error } = useQuery({
    queryKey: ['cluster-recommendations', clusterId],
    queryFn: () => getClusterRecommendations(clusterId),
    refetchInterval: 30_000,
    enabled: !!clusterId,
  });

  const handleRefresh = async () => {
    try {
      await refreshClusterRecommendations(clusterId);
      queryClient.invalidateQueries({ queryKey: ['cluster-recommendations', clusterId] });
    } catch {
      // silent
    }
  };

  // Group recommendations into tiered sections
  const sections = useMemo(() => {
    if (!snapshot) return [];
    const recs = snapshot.scored_recommendations;
    const used = new Set<string>();

    return sectionConfig.map((sec) => {
      const items: ScoredRecommendationDTO[] = [];
      for (const rec of recs) {
        if (used.has(rec.recommendation_id)) continue;
        const catMatch = sec.categories ? sec.categories.some((c) => rec.category.toLowerCase().includes(c)) : false;
        const sevMatch = sec.severities ? sec.severities.includes(rec.severity.toLowerCase()) : false;

        if (sec.categories && sec.severities) {
          // Critical section: match severity OR category
          if (sevMatch || catMatch) {
            items.push(rec);
            used.add(rec.recommendation_id);
          }
        } else if (sec.categories) {
          if (catMatch) {
            items.push(rec);
            used.add(rec.recommendation_id);
          }
        } else {
          // Catch-all for remaining
          items.push(rec);
          used.add(rec.recommendation_id);
        }
      }
      return { ...sec, items };
    }).filter((s) => s.items.length > 0);
  }, [snapshot]);

  const timeAgo = (iso: string) => {
    if (!iso) return 'Never';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: '#1a1814' }}>
        <span className="material-symbols-outlined text-[#e09f3e] animate-spin text-2xl">progress_activity</span>
        <span className="ml-3 text-sm text-slate-400">Loading recommendations...</span>
      </div>
    );
  }

  if (error || !snapshot) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center" style={{ background: '#1a1814' }}>
        <span className="material-symbols-outlined text-red-400 text-2xl mb-2">error</span>
        <p className="text-sm text-red-400 mb-4">Failed to load recommendations</p>
        <button
          onClick={onBack}
          className="px-4 py-2 text-xs bg-[#252118] text-slate-300 border border-[#3d3528] rounded hover:bg-[#3d3528] transition-colors"
        >
          Back to Fleet
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar" style={{ background: '#1a1814' }}>
      <div className="max-w-[1200px] mx-auto px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 text-slate-400 hover:text-slate-200 transition-colors"
              title="Back to Fleet"
            >
              <span className="material-symbols-outlined text-[20px]">arrow_back</span>
            </button>
            <div>
              <h1 className="text-lg font-display font-bold text-slate-100">{snapshot.cluster_name}</h1>
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span className="uppercase font-medium">{snapshot.provider}</span>
                <span>&middot;</span>
                <span>Last scan: {timeAgo(snapshot.scanned_at)}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="p-2 text-slate-400 hover:text-[#e09f3e] transition-colors"
              title="Refresh Recommendations"
            >
              <span className="material-symbols-outlined text-[18px]">refresh</span>
            </button>
            <button
              onClick={onBack}
              className="px-3 py-1.5 text-[11px] font-medium bg-[#252118] text-slate-300 border border-[#3d3528] rounded hover:bg-[#3d3528] transition-colors"
            >
              Back to Fleet
            </button>
          </div>
        </div>

        {/* Top Banner */}
        <div className="flex items-center gap-4 mb-6 px-5 py-3 bg-[#13110d] border border-[#3d3528]/30 rounded-lg">
          {snapshot.critical_count > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              <span className="text-sm font-medium text-red-400">{snapshot.critical_count} Critical</span>
            </div>
          )}
          {snapshot.optimization_count > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-sm font-medium text-[#e09f3e]">{snapshot.optimization_count} Optimizations</span>
            </div>
          )}
          {snapshot.security_count > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-yellow-500" />
              <span className="text-sm font-medium text-yellow-400">{snapshot.security_count} Security</span>
            </div>
          )}
          <div className="flex-1" />
          {snapshot.total_savings_usd > 0 && (
            <span className="text-sm font-bold text-green-400">
              ${snapshot.total_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })} potential savings
            </span>
          )}
        </div>

        {/* Tiered Sections */}
        {sections.map((section) => (
          <div key={section.key} className="mb-6">
            <div
              className="flex items-center gap-2 mb-3 pl-3"
              style={{ borderLeft: `3px solid ${section.borderColor}` }}
            >
              <h2 className="text-sm font-display font-bold text-slate-200">{section.label}</h2>
              <span className="text-[10px] text-slate-500">({section.items.length})</span>
            </div>
            <div className={`space-y-2 ${section.key === 'known' ? 'opacity-70' : ''}`}>
              {section.items.map((rec) => (
                <RecommendationCard key={rec.recommendation_id} rec={rec} />
              ))}
            </div>
          </div>
        ))}

        {/* Empty recommendations state */}
        {snapshot.scored_recommendations.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <span className="material-symbols-outlined text-green-500 mb-3" style={{ fontSize: 48 }}>check_circle</span>
            <p className="text-sm text-slate-300 mb-1">No recommendations at this time.</p>
            <p className="text-xs text-slate-500">This cluster looks healthy. Run a fresh scan to check again.</p>
          </div>
        )}

        {/* Cost Breakdown */}
        {snapshot.cost_summary && (
          <div className="mt-6">
            <CostBreakdownPanel cost={snapshot.cost_summary} />
          </div>
        )}
      </div>
    </div>
  );
};

export default ClusterRecommendationsPage;
