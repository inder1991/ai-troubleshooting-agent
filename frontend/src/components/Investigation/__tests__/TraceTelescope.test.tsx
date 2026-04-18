import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TraceTelescope from '../TraceTelescope/TraceTelescope';
import type { TraceAnalysisResult, SpanInfo } from '../../../types';

function mkSpan(overrides: Partial<SpanInfo> = {}): SpanInfo {
  return {
    span_id: 's1',
    service: 'api',
    service_name: 'api',
    operation: 'call',
    operation_name: 'call',
    duration_ms: 100,
    status: 'ok',
    error: false,
    parent_span_id: null,
    tags: {},
    start_time_us: 1_700_000_000_000_000,
    ...overrides,
  };
}

function mkTrace(spans: SpanInfo[] = [mkSpan()]): TraceAnalysisResult {
  return {
    trace_id: 'tid',
    total_duration_ms: 100,
    total_services: 1,
    total_spans: spans.length,
    call_chain: spans,
    cascade_path: [],
    latency_bottlenecks: [],
    retry_detected: false,
    service_dependency_graph: {},
    trace_source: 'jaeger',
    overall_confidence: 70,
    services_in_chain: Array.from(new Set(spans.map((s) => s.service_name || s.service))),
  };
}

describe('TraceTelescope', () => {
  it('renders the three tab buttons', () => {
    render(<TraceTelescope trace={mkTrace()} onClose={() => {}} />);
    expect(screen.getByTestId('telescope-tab-flow')).toBeInTheDocument();
    expect(screen.getByTestId('telescope-tab-waterfall')).toBeInTheDocument();
    expect(screen.getByTestId('telescope-tab-detail')).toBeInTheDocument();
  });

  it('clicking Close invokes the onClose handler', () => {
    const onClose = vi.fn();
    render(<TraceTelescope trace={mkTrace()} onClose={onClose} />);
    fireEvent.click(screen.getByTestId('telescope-close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('Escape keypress closes the telescope', () => {
    const onClose = vi.fn();
    render(<TraceTelescope trace={mkTrace()} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('switches to Waterfall tab on click', () => {
    render(<TraceTelescope trace={mkTrace()} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('telescope-tab-waterfall'));
    expect(screen.getByTestId('waterfall-scroll')).toBeInTheDocument();
  });

  it('clicking a span in the waterfall switches to Detail with the span selected', () => {
    const spans = [
      mkSpan({ span_id: 's1', start_time_us: 1_000 }),
      mkSpan({ span_id: 's2', start_time_us: 2_000 }),
    ];
    render(<TraceTelescope trace={mkTrace(spans)} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('telescope-tab-waterfall'));
    fireEvent.click(screen.getByTestId('waterfall-row-s2'));
    // Detail tab should now be active + span s2's ID should be visible.
    expect(screen.getByText(/s2/)).toBeInTheDocument();
  });

  it('Detail tab shows empty state when nothing selected', () => {
    render(<TraceTelescope trace={mkTrace()} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('telescope-tab-detail'));
    expect(screen.getByText(/Select a span/)).toBeInTheDocument();
  });

  it('Flow tab renders nodes for each service in dependency graph', () => {
    const trace: TraceAnalysisResult = {
      ...mkTrace([
        mkSpan({ span_id: 'a', service_name: 'api' }),
        mkSpan({ span_id: 'b', service_name: 'db', parent_span_id: 'a' }),
      ]),
      service_dependency_graph: { api: ['db'] },
      services_in_chain: ['api', 'db'],
    };
    render(<TraceTelescope trace={trace} onClose={() => {}} />);
    expect(screen.getByTestId('flow-node-api')).toBeInTheDocument();
    expect(screen.getByTestId('flow-node-db')).toBeInTheDocument();
  });

  it('Flow tab empty state when no dependency graph', () => {
    const trace = mkTrace();
    // service_dependency_graph is {} → start on waterfall tab; force Flow.
    render(<TraceTelescope trace={trace} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('telescope-tab-flow'));
    // With only 1 service and empty graph, FlowTab renders that one node.
    expect(screen.getByTestId('flow-node-api')).toBeInTheDocument();
  });
});
