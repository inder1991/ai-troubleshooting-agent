import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BlastRadiusList, _internals } from '../BlastRadiusList';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import {
  TopologySelectionProvider,
  useTopologySelection,
} from '../../../contexts/TopologySelectionContext';
import type { V4Findings, V4SessionStatus, BlastRadiusData, MetricAnomaly, DiagnosticPhase } from '../../../types';

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

function status(phase: DiagnosticPhase = 'collecting_context', updatedAt = '2026-04-19T00:00:00Z'): V4SessionStatus {
  return {
    session_id: 's',
    service_name: 'svc',
    phase,
    confidence: 0,
    findings_count: 0,
    token_usage: [],
    breadcrumbs: [],
    created_at: updatedAt,
    updated_at: updatedAt,
    pending_action: null,
  };
}

function blast(over: Partial<BlastRadiusData> = {}): BlastRadiusData {
  return {
    primary_service: 'checkout-service',
    upstream_affected: [],
    downstream_affected: [],
    shared_resources: [],
    estimated_user_impact: '',
    scope: 'service_group',
    ...over,
  };
}

function anomaly(over: Partial<MetricAnomaly> = {}): MetricAnomaly {
  const now = new Date();
  return {
    metric_name: 'errors',
    promql_query: 'rate(errors{service="auth-service"}[5m])',
    baseline_value: 0,
    peak_value: 1,
    spike_start: now,
    spike_end: now,
    severity: 'high',
    correlation_to_incident: '',
    confidence_score: 80,
    ...over,
  } as MetricAnomaly;
}

function Harness({
  f,
  s,
  now,
}: {
  f: V4Findings | null;
  s?: V4SessionStatus | null;
  now?: number;
}) {
  return (
    <IncidentLifecycleProvider status={s ?? null} now={now}>
      <TopologySelectionProvider>
        <BlastRadiusList findings={f} />
      </TopologySelectionProvider>
    </IncidentLifecycleProvider>
  );
}

describe('BlastRadiusList', () => {
  it('renders nothing when findings.blast_radius is absent', () => {
    const { container } = render(<Harness f={findings()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when all tiers are empty', () => {
    const { container } = render(<Harness f={findings({ blast_radius: blast() })} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the service list grouped by tier', () => {
    const br = blast({
      upstream_affected: ['auth-service'],
      downstream_affected: ['payments-api'],
      shared_resources: ['redis-cluster'],
    });
    render(<Harness f={findings({ blast_radius: br })} />);
    expect(screen.getByTestId('blast-radius-list')).toBeInTheDocument();
    expect(screen.getByTestId('blast-radius-row-auth-service')).toBeInTheDocument();
    expect(screen.getByTestId('blast-radius-row-payments-api')).toBeInTheDocument();
    expect(screen.getByTestId('blast-radius-row-redis-cluster')).toBeInTheDocument();
  });

  it('unknown status when service has no signals in findings', () => {
    render(
      <Harness
        f={findings({ blast_radius: blast({ upstream_affected: ['lonely-svc'] }) })}
      />,
    );
    expect(
      screen.getByTestId('blast-radius-status-lonely-svc').textContent,
    ).toMatch(/unknown/);
  });

  it('degraded status when a recent metric anomaly references the service', () => {
    const now = Date.now();
    const recent = new Date(now - 60 * 1000); // 1min ago
    render(
      <Harness
        f={findings({
          blast_radius: blast({ upstream_affected: ['auth-service'] }),
          metric_anomalies: [
            anomaly({
              spike_end: recent,
              promql_query: 'rate(errors{service="auth-service"}[5m])',
            }),
          ],
        })}
      />,
    );
    expect(
      screen.getByTestId('blast-radius-status-auth-service').textContent,
    ).toMatch(/degraded/);
  });

  it('stale status when last signal is > 5 minutes old (active lifecycle)', () => {
    const now = Date.now();
    const old = new Date(now - 10 * 60 * 1000); // 10min ago
    render(
      <Harness
        f={findings({
          blast_radius: blast({ upstream_affected: ['auth-service'] }),
          metric_anomalies: [
            anomaly({
              spike_end: old,
              promql_query: 'rate(errors{service="auth-service"}[5m])',
            }),
          ],
        })}
      />,
    );
    expect(
      screen.getByTestId('blast-radius-status-auth-service').textContent,
    ).toMatch(/stale/);
  });

  it('historical lifecycle uses -at-close statuses', () => {
    const nowWall = Date.parse('2026-04-19T12:00:00Z');
    const old = new Date(Date.parse('2026-04-19T00:00:00Z'));
    render(
      <Harness
        f={findings({
          blast_radius: blast({ upstream_affected: ['auth-service'] }),
          metric_anomalies: [
            anomaly({
              spike_end: old,
              promql_query: 'rate(errors{service="auth-service"}[5m])',
            }),
          ],
        })}
        s={status('complete', '2026-04-19T00:00:00Z')}
        now={nowWall}
      />,
    );
    const txt = screen.getByTestId('blast-radius-status-auth-service').textContent ?? '';
    expect(txt).toMatch(/at close/);
  });

  it('clicking a row triggers topology selection', () => {
    function Probe() {
      const { selectedService } = useTopologySelection();
      return <div data-testid="probe">{selectedService ?? 'none'}</div>;
    }
    render(
      <IncidentLifecycleProvider status={null}>
        <TopologySelectionProvider>
          <BlastRadiusList
            findings={findings({
              blast_radius: blast({ upstream_affected: ['auth-service'] }),
            })}
          />
          <Probe />
        </TopologySelectionProvider>
      </IncidentLifecycleProvider>,
    );
    expect(screen.getByTestId('probe').textContent).toBe('none');
    fireEvent.click(screen.getByTestId('blast-radius-row-auth-service'));
    expect(screen.getByTestId('probe').textContent).toBe('auth-service');
  });
});

describe('BlastRadiusList._internals.deriveStatus', () => {
  const br = blast({ upstream_affected: ['a'] });

  it('returns unknown when no signals', () => {
    const s = _internals.deriveStatus('a', findings({ blast_radius: br }), false);
    expect(s).toBe('unknown');
  });

  it('returns degraded for recent signals', () => {
    const now = Date.now();
    const recent = new Date(now - 60_000);
    const s = _internals.deriveStatus(
      'a',
      findings({
        blast_radius: br,
        metric_anomalies: [
          anomaly({ promql_query: 'up{service="a"}', spike_end: recent }),
        ],
      }),
      false,
      now,
    );
    expect(s).toBe('degraded');
  });

  it('returns stale for old signals under active lifecycle', () => {
    const now = Date.now();
    const old = new Date(now - 10 * 60_000);
    const s = _internals.deriveStatus(
      'a',
      findings({
        blast_radius: br,
        metric_anomalies: [
          anomaly({ promql_query: 'up{service="a"}', spike_end: old }),
        ],
      }),
      false,
      now,
    );
    expect(s).toBe('stale');
  });

  it('returns recovered-at-close for historical incidents', () => {
    const s = _internals.deriveStatus(
      'a',
      findings({ blast_radius: br }), // no signals at all
      true,
    );
    expect(s).toBe('recovered-at-close');
  });
});
