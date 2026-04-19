import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReproduceQueryRow } from '../ReproduceQueryRow';
import type { MetricAnomaly, SuggestedPromQLQuery } from '../../../types';

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
});
