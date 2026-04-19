import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReproduceQueryRow } from '../ReproduceQueryRow';
import { IncidentLifecycleProvider } from '../../../contexts/IncidentLifecycleContext';
import type { MetricAnomaly, SuggestedPromQLQuery, V4SessionStatus } from '../../../types';
import * as apiModule from '../../../services/api';

function anomaly(over: Partial<MetricAnomaly> = {}): MetricAnomaly {
  const now = new Date();
  return {
    metric_name: 'http_errors_total',
    promql_query: 'rate(http_errors_total[5m])',
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

function query(metric = 'http_errors_total'): SuggestedPromQLQuery {
  return {
    metric,
    query: `rate(${metric}[5m])`,
    rationale: 'test',
  };
}

describe('ReproduceQueryRow', () => {
  it('renders nothing when no matching query exists', () => {
    const { container } = render(
      <ReproduceQueryRow anomaly={anomaly()} queries={[]} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders copy + run inline actions when query matches by metric name', () => {
    render(
      <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />,
    );
    expect(screen.getByTestId('reproduce-copy')).toBeInTheDocument();
    expect(screen.getByTestId('reproduce-run')).toBeInTheDocument();
  });

  it('matches case-insensitively when exact match fails', () => {
    render(
      <ReproduceQueryRow
        anomaly={anomaly({ metric_name: 'HTTP_ERRORS_TOTAL' })}
        queries={[query('http_errors_total')]}
      />,
    );
    expect(screen.getByTestId('reproduce-copy')).toBeInTheDocument();
  });

  it('prefix-matches when no exact / ci match', () => {
    render(
      <ReproduceQueryRow
        anomaly={anomaly({ metric_name: 'http_errors_total_service_payments' })}
        queries={[query('http_errors_total')]}
      />,
    );
    expect(screen.getByTestId('reproduce-copy')).toBeInTheDocument();
  });

  it('copy action writes to clipboard when available', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    render(
      <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />,
    );
    fireEvent.click(screen.getByTestId('reproduce-copy'));
    expect(writeText).toHaveBeenCalledWith('rate(http_errors_total[5m])');
  });

  it('copy action degrades gracefully when clipboard denies', () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: () => { throw new Error('denied'); },
      },
      configurable: true,
    });
    render(
      <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />,
    );
    // Shouldn't throw
    fireEvent.click(screen.getByTestId('reproduce-copy'));
  });

  it('row text uses editorial italic and "reproduce" prose (no pills)', () => {
    render(
      <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />,
    );
    const row = screen.getByTestId(`reproduce-row-${anomaly().metric_name}`);
    expect(row.textContent).toMatch(/reproduce/);
    expect(row.innerHTML).toMatch(/font-editorial/);
    expect(row.innerHTML).not.toMatch(/rounded-full/);
  });

  // ── PR-C: historical lifecycle gate ────────────────────────────────

  function historicalStatus(): V4SessionStatus {
    return {
      session_id: 's',
      service_name: 'svc',
      phase: 'complete',
      confidence: 80,
      findings_count: 0,
      token_usage: [],
      breadcrumbs: [],
      created_at: '2026-04-17T00:00:00Z',
      updated_at: '2026-04-17T00:00:00Z',
      pending_action: null,
    };
  }

  it('disables Run + does not call API when investigation is historical', async () => {
    const spy = vi.spyOn(apiModule, 'runPromQLQuery').mockResolvedValue({
      data_points: [],
      current_value: 0,
    } as any);

    // now 48h after updated_at → bucket = historical
    const now = Date.parse('2026-04-19T00:00:00Z');
    render(
      <IncidentLifecycleProvider status={historicalStatus()} now={now}>
        <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />
      </IncidentLifecycleProvider>,
    );
    const runBtn = screen.getByTestId('reproduce-run');
    expect(runBtn).toBeDisabled();
    expect(runBtn.getAttribute('data-historical')).toBe('true');

    fireEvent.click(runBtn);
    expect(spy).not.toHaveBeenCalled();
  });

  it('keeps Run enabled when lifecycle is recent (within 6h of close)', () => {
    // 1h after updated_at → bucket = recent
    const now = Date.parse('2026-04-17T01:00:00Z');
    render(
      <IncidentLifecycleProvider status={historicalStatus()} now={now}>
        <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />
      </IncidentLifecycleProvider>,
    );
    const runBtn = screen.getByTestId('reproduce-run');
    expect(runBtn).not.toBeDisabled();
    expect(runBtn.getAttribute('data-historical')).toBeNull();
  });

  it('keeps Copy enabled even when historical (clipboard is not a live side effect)', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
    const now = Date.parse('2026-04-19T00:00:00Z');
    render(
      <IncidentLifecycleProvider status={historicalStatus()} now={now}>
        <ReproduceQueryRow anomaly={anomaly()} queries={[query()]} />
      </IncidentLifecycleProvider>,
    );
    fireEvent.click(screen.getByTestId('reproduce-copy'));
    expect(writeText).toHaveBeenCalledWith('rate(http_errors_total[5m])');
  });
});
