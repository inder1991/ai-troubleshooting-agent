import React, { useState, useCallback } from 'react';
import { API_BASE_URL } from '../../services/api';

interface ClusterDossierExportProps {
  sessionId: string;
  platformHealth: string;
}

const ClusterDossierExport: React.FC<ClusterDossierExportProps> = ({ sessionId, platformHealth }) => {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportDossier = useCallback(async (format: 'json' | 'text') => {
    setExporting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/cluster-dossier`);
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      const { dossier } = await res.json();
      if (!dossier) throw new Error('No dossier data available');

      let content: string;
      let filename: string;
      let mimeType: string;

      if (format === 'json') {
        content = JSON.stringify(dossier, null, 2);
        filename = `cluster-dossier-${sessionId.slice(0, 8)}.json`;
        mimeType = 'application/json';
      } else {
        content = formatDossierAsText(dossier);
        filename = `cluster-dossier-${sessionId.slice(0, 8)}.txt`;
        mimeType = 'text/plain';
      }

      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  }, [sessionId]);

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => exportDossier('text')}
        disabled={exporting || platformHealth === 'PENDING'}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-wr-accent/30 text-wr-accent hover:bg-wr-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span className="material-symbols-outlined text-[14px]">description</span>
        {exporting ? 'Exporting...' : 'Export Report'}
      </button>
      <button
        onClick={() => exportDossier('json')}
        disabled={exporting || platformHealth === 'PENDING'}
        className="flex items-center gap-1.5 px-2 py-1.5 text-xs rounded border border-slate-600/30 text-slate-400 hover:bg-slate-600/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        title="Export as JSON"
      >
        <span className="material-symbols-outlined text-[14px]">data_object</span>
      </button>
      {error && <span className="text-[10px] text-red-400">{error}</span>}
    </div>
  );
};

function formatDossierAsText(dossier: any): string {
  const lines: string[] = [];
  const hr = '\u2500'.repeat(60);

  lines.push('CLUSTER DIAGNOSTIC REPORT');
  lines.push(`Generated: ${dossier.generated_at}`);
  lines.push(`Session: ${dossier.session_id}`);
  lines.push(hr);

  // Executive Summary
  const es = dossier.executive_summary;
  lines.push('');
  lines.push('EXECUTIVE SUMMARY');
  lines.push(hr);
  lines.push(`Platform: ${es.platform} ${es.platform_version}`);
  lines.push(`Health Status: ${es.health_status}`);
  lines.push(`Data Completeness: ${(es.data_completeness * 100).toFixed(0)}%`);
  lines.push(`Total Anomalies: ${es.total_anomalies}`);
  lines.push(`Causal Chains: ${es.causal_chains_found}`);
  lines.push(`Scan Mode: ${es.scan_mode}`);

  // Domain Reports
  lines.push('');
  lines.push('DOMAIN REPORTS');
  lines.push(hr);
  for (const domain of dossier.domain_reports || []) {
    lines.push('');
    lines.push(`  ${domain.domain.toUpperCase()} (${domain.status}, confidence: ${domain.confidence}%, ${domain.duration_ms}ms)`);
    if (domain.anomalies.length === 0) {
      lines.push('    No anomalies detected');
    }
    for (const anomaly of domain.anomalies) {
      lines.push(`    [${anomaly.severity?.toUpperCase() || 'MEDIUM'}] ${anomaly.description}`);
      lines.push(`      Evidence: ${anomaly.evidence_ref}`);
    }
    if (domain.ruled_out.length > 0) {
      lines.push(`    Ruled out: ${domain.ruled_out.join(', ')}`);
    }
    // Truncation warnings
    const trunc = domain.truncation_flags || {};
    const truncated = Object.entries(trunc).filter(([_, v]) => v).map(([k]) => k);
    if (truncated.length > 0) {
      lines.push(`    \u26A0 Data truncated: ${truncated.join(', ')}`);
    }
  }

  // Causal Analysis
  lines.push('');
  lines.push('CAUSAL ANALYSIS');
  lines.push(hr);
  const chains = dossier.causal_analysis?.chains || [];
  if (chains.length === 0) {
    lines.push('  No causal chains identified');
  }
  for (const chain of chains) {
    lines.push('');
    lines.push(`  Chain ${chain.chain_id} (confidence: ${(chain.confidence * 100).toFixed(0)}%)`);
    lines.push(`    ROOT CAUSE: ${chain.root_cause?.description || 'Unknown'}`);
    for (const effect of chain.cascading_effects || []) {
      lines.push(`    \u2192 ${effect.description} (${effect.link_type})`);
    }
  }

  // Uncorrelated findings
  const uncorr = dossier.causal_analysis?.uncorrelated_findings || [];
  if (uncorr.length > 0) {
    lines.push('');
    lines.push('  Uncorrelated Findings:');
    for (const f of uncorr) {
      lines.push(`    - [${f.severity?.toUpperCase() || 'MEDIUM'}] ${f.description}`);
    }
  }

  // Blast Radius
  if (dossier.blast_radius?.summary) {
    lines.push('');
    lines.push('BLAST RADIUS');
    lines.push(hr);
    lines.push(`  ${dossier.blast_radius.summary}`);
    lines.push(`  Affected: ${dossier.blast_radius.affected_pods || 0} pods, ${dossier.blast_radius.affected_nodes || 0} nodes, ${dossier.blast_radius.affected_namespaces || 0} namespaces`);
  }

  // Remediation
  lines.push('');
  lines.push('REMEDIATION');
  lines.push(hr);
  const immediate = dossier.remediation?.immediate || [];
  if (immediate.length > 0) {
    lines.push('  Immediate Actions:');
    for (const step of immediate) {
      lines.push(`    ${step.description}`);
      if (step.command) lines.push(`      $ ${step.command}`);
      if (step.risk_level) lines.push(`      Risk: ${step.risk_level}`);
    }
  }
  const longTerm = dossier.remediation?.long_term || [];
  if (longTerm.length > 0) {
    lines.push('  Long-Term Recommendations:');
    for (const step of longTerm) {
      lines.push(`    - ${step.description}`);
      if (step.effort_estimate) lines.push(`      Effort: ${step.effort_estimate}`);
    }
  }

  lines.push('');
  lines.push(hr);
  lines.push('End of Report');

  return lines.join('\n');
}

export default ClusterDossierExport;
