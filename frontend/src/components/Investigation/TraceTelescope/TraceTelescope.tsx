import React, { useState, useEffect } from 'react';
import type { TraceAnalysisResult } from '../../../types';
import FlowTab from './FlowTab';
import WaterfallTab from './WaterfallTab';
import DetailTab from './DetailTab';
import { useTraceSelection } from './useTraceSelection';

interface TraceTelescopeProps {
  trace: TraceAnalysisResult;
  initialServiceFilter?: string | null;
  backendUrl?: string;
  onClose: () => void;
}

type Tab = 'flow' | 'waterfall' | 'detail';

/**
 * Full-screen overlay with 3 temporally-ordered tabs:
 *   Flow       "what did the request touch?"
 *   Waterfall  "where was the time spent?"
 *   Detail     "what do I do with this span?"
 *
 * Single shared selection state across all tabs (see useTraceSelection).
 * Click Escape or the × button to close.
 */
export default function TraceTelescope(props: TraceTelescopeProps) {
  const { trace, initialServiceFilter, backendUrl, onClose } = props;

  const [activeTab, setActiveTab] = useState<Tab>(
    trace.service_dependency_graph && Object.keys(trace.service_dependency_graph).length > 0
      ? 'flow'
      : 'waterfall',
  );
  const selection = useTraceSelection(trace.call_chain);

  // Seed service filter from caller (e.g. "opened from Navigator badge").
  useEffect(() => {
    if (initialServiceFilter) {
      selection.selectService(initialServiceFilter);
    }
  }, [initialServiceFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // Escape to close.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Clicking a span in Flow/Waterfall auto-switches to Detail.
  useEffect(() => {
    if (selection.selectedSpanId && activeTab !== 'detail') {
      // Don't auto-switch on first render — only when user actively picks a span.
    }
  }, [selection.selectedSpanId]); // eslint-disable-line react-hooks/exhaustive-deps

  const failureService = trace.failure_point?.service_name ?? trace.failure_point?.service;
  const provenanceBadge = provenanceFor(trace);

  return (
    <div
      className="fixed inset-0 z-50 bg-wr-bg-deep/95 flex flex-col"
      role="dialog"
      aria-label="Trace Telescope"
      data-testid="trace-telescope"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-wr-border bg-wr-bg/80 backdrop-blur">
        <div>
          <p className="text-body-xs text-wr-text-muted font-mono">Trace {trace.trace_id}</p>
          <div className="flex items-center gap-2 mt-1 text-body-xs">
            <span className={`px-2 py-0.5 rounded border ${provenanceBadge.cls}`}>
              {provenanceBadge.label}
            </span>
            {trace.sampling_mode && (
              <span className="text-wr-text-muted">· {trace.sampling_mode}</span>
            )}
            <span className="text-wr-text-muted">· {trace.total_spans} spans</span>
            <span className="text-wr-text-muted">· {Math.round(trace.total_duration_ms)}ms</span>
            <span className="text-wr-text-muted">· {trace.overall_confidence}% confidence</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-wr-text-muted hover:text-wr-text px-2 py-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-wr-accent"
          data-testid="telescope-close"
        >
          ×
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-wr-border bg-wr-bg/60">
        <TabButton
          tab="flow"
          active={activeTab}
          onClick={setActiveTab}
          label="Flow"
          count={Object.keys(trace.service_dependency_graph || {}).length}
        />
        <TabButton
          tab="waterfall"
          active={activeTab}
          onClick={setActiveTab}
          label="Waterfall"
          count={trace.call_chain.length}
        />
        <TabButton
          tab="detail"
          active={activeTab}
          onClick={setActiveTab}
          label="Detail"
          highlight={!!selection.selectedSpanId}
        />
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'flow' && (
          <FlowTab
            spans={trace.call_chain}
            dependencyGraph={trace.service_dependency_graph || {}}
            servicesInChain={trace.services_in_chain || []}
            failureService={failureService}
            hotServices={trace.hot_services || []}
            bottleneckOperations={trace.bottleneck_operations || []}
            cascadePath={trace.cascade_path || []}
            selectedServiceFilter={selection.selectedServiceFilter}
            onSelectService={selection.selectService}
          />
        )}
        {activeTab === 'waterfall' && (
          <WaterfallTab
            spans={trace.call_chain}
            serviceFilter={selection.selectedServiceFilter}
            selectedSpanId={selection.selectedSpanId}
            onSelectSpan={(id) => {
              selection.selectSpan(id);
              if (id) setActiveTab('detail');
            }}
          />
        )}
        {activeTab === 'detail' && (
          <DetailTab
            span={selection.selectedSpan}
            traceId={trace.trace_id}
            backendUrl={backendUrl}
          />
        )}
      </div>
    </div>
  );
}

function TabButton({
  tab, active, onClick, label, count, highlight,
}: {
  tab: Tab;
  active: Tab;
  onClick: (t: Tab) => void;
  label: string;
  count?: number;
  highlight?: boolean;
}) {
  const isActive = active === tab;
  return (
    <button
      type="button"
      onClick={() => onClick(tab)}
      data-testid={`telescope-tab-${tab}`}
      className={`px-4 py-2 text-sm border-b-2 transition-colors ${
        isActive
          ? 'border-wr-accent text-wr-text'
          : 'border-transparent text-wr-text-muted hover:text-wr-text'
      } ${highlight && !isActive ? 'after:inline-block after:w-1.5 after:h-1.5 after:rounded-full after:bg-wr-accent after:ml-2' : ''}`}
    >
      {label}
      {typeof count === 'number' && count > 0 && (
        <span className="ml-2 text-body-xs text-wr-text-muted">{count}</span>
      )}
    </button>
  );
}

function provenanceFor(trace: TraceAnalysisResult): { label: string; cls: string } {
  switch (trace.trace_source) {
    case 'jaeger':
      return { label: 'Jaeger-native', cls: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' };
    case 'tempo':
      return { label: 'Tempo-native', cls: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' };
    case 'summarized':
      return { label: 'Summarized', cls: 'border-wr-accent/50 text-wr-accent bg-wr-accent/10' };
    case 'elasticsearch': {
      const conf = trace.elk_reconstruction_confidence ?? 0;
      return {
        label: `ELK-reconstructed · ${conf}%`,
        cls: 'border-orange-500/40 text-orange-300 bg-orange-500/10',
      };
    }
    default:
      return { label: trace.trace_source, cls: 'border-wr-border text-wr-text-muted' };
  }
}
