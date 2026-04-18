import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TracingEvidenceCard from '../cards/TracingEvidenceCard';
import type { TraceAnalysisResult, SpanInfo } from '../../../types';

function mkSpan(overrides: Partial<SpanInfo> = {}): SpanInfo {
  return {
    span_id: 's1',
    service: 'api',
    service_name: 'api',
    operation: 'GET /x',
    operation_name: 'GET /x',
    duration_ms: 100,
    status: 'ok',
    error: false,
    parent_span_id: null,
    tags: {},
    start_time_us: 1_700_000_000_000_000,
    ...overrides,
  };
}

function mkTrace(overrides: Partial<TraceAnalysisResult> = {}): TraceAnalysisResult {
  return {
    trace_id: 'trace-abc',
    total_duration_ms: 2000,
    total_services: 3,
    total_spans: 30,
    call_chain: [mkSpan()],
    cascade_path: [],
    latency_bottlenecks: [],
    retry_detected: false,
    service_dependency_graph: {},
    trace_source: 'jaeger',
    overall_confidence: 82,
    services_in_chain: ['api', 'inventory', 'db'],
    hot_services: ['inventory'],
    envoy_findings: [],
    pattern_findings: [],
    tier_decision: { tier: 1, rationale: 'x', model_key: 'cheap' },
    mined_trace_ids: [],
    ...overrides,
  };
}

describe('TracingEvidenceCard', () => {
  it('renders the provenance badge based on trace_source', () => {
    render(<TracingEvidenceCard trace={mkTrace({ trace_source: 'tempo' })} />);
    expect(screen.getByTestId('provenance-badge').textContent).toContain('Tempo-native');
  });

  it('shows ELK-reconstructed badge with confidence when that is the source', () => {
    render(
      <TracingEvidenceCard
        trace={mkTrace({
          trace_source: 'elasticsearch',
          elk_reconstruction_confidence: 55,
        })}
      />,
    );
    expect(screen.getByTestId('provenance-badge').textContent).toContain('ELK-reconstructed');
    expect(screen.getByTestId('provenance-badge').textContent).toContain('55%');
  });

  it('renders pattern finding pills with metadata', () => {
    const trace = mkTrace({
      pattern_findings: [
        {
          kind: 'n_plus_one', confidence: 80, severity: 'high',
          human_summary: 'N+1 in db.SELECT', service_name: 'db',
          span_ids_involved: [], metadata: { child_count: 47 }, deterministic: true,
        },
        {
          kind: 'fan_out_amplification', confidence: 75, severity: 'medium',
          human_summary: 'Fan-out', service_name: 'x', span_ids_involved: [],
          metadata: { amplification_factor: 4.3 }, deterministic: true,
        },
      ],
    });
    render(<TracingEvidenceCard trace={trace} />);
    const patterns = screen.getByTestId('pattern-findings');
    expect(patterns.textContent).toContain('N+1 ×47');
    expect(patterns.textContent).toContain('Fan-out 4.3×');
  });

  it('renders Envoy flag badges when present', () => {
    const trace = mkTrace({
      envoy_findings: [
        {
          flag: 'UH', span_id: 's1', service_name: 'inventory',
          human_summary: 'no healthy upstream', likely_cause: 'no pods',
          deterministic: true,
        },
      ],
    });
    render(<TracingEvidenceCard trace={trace} />);
    const envoy = screen.getByTestId('envoy-flags');
    expect(envoy.textContent).toContain('UH');
    expect(envoy.textContent).toContain('inventory');
  });

  it('Explore button toggles the telescope', () => {
    render(<TracingEvidenceCard trace={mkTrace()} />);
    expect(screen.queryByTestId('trace-telescope')).toBeNull();
    fireEvent.click(screen.getByTestId('open-telescope'));
    expect(screen.getByTestId('trace-telescope')).toBeInTheDocument();
  });

  it('labels services as failure/hot/normal correctly', () => {
    const trace = mkTrace({
      failure_point: mkSpan({ span_id: 'f', service_name: 'payments' }),
      services_in_chain: ['api', 'payments', 'inventory'],
      hot_services: ['inventory'],
    });
    const { container } = render(<TracingEvidenceCard trace={trace} />);
    expect(container.textContent).toContain('payments');
    expect(container.textContent).toContain('inventory');
  });
});
