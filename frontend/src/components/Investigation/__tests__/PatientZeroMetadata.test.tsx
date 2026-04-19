import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PatientZeroMetadata from '../PatientZeroMetadata';
import type { V4Findings, PodHealthStatus, PatientZero } from '../../../types';

function pod(over: Partial<PodHealthStatus> = {}): PodHealthStatus {
  return {
    pod_name: 'p-1',
    namespace: 'checkout-prod',
    status: 'Running',
    restart_count: 0,
    ready: true,
    conditions: [],
    oom_killed: false,
    crash_loop: false,
    ...over,
  };
}

function pz(service: string): PatientZero {
  return {
    service,
    evidence: 'errors started here',
    first_error_time: '2026-04-19T00:00:00Z',
  };
}

function findings(over: Partial<V4Findings> = {}): V4Findings {
  return { session_id: 's', findings: [], ...over };
}

describe('PatientZeroMetadata', () => {
  // ── Absence ──────────────────────────────────────────────────────

  it('renders nothing when no data', () => {
    const { container } = render(<PatientZeroMetadata findings={findings()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when service unknown and no namespace', () => {
    const { container } = render(
      <PatientZeroMetadata findings={findings({ patient_zero: pz('unknown-svc-xyz') })} />,
    );
    expect(container.firstChild).toBeNull();
  });

  // ── Env context line ─────────────────────────────────────────────

  it('renders env line with just namespace when that is all we have', () => {
    render(
      <PatientZeroMetadata
        findings={findings({
          patient_zero: pz('unknown-svc-xyz'),
          pod_statuses: [pod({ namespace: 'checkout-prod' })],
        })}
      />,
    );
    expect(screen.getByTestId('patient-zero-env')).toHaveTextContent('ns/checkout-prod');
  });

  it('does not render env line when namespace is empty string', () => {
    render(
      <PatientZeroMetadata
        findings={findings({
          patient_zero: pz('unknown-svc-xyz'),
          pod_statuses: [pod({ namespace: '' })],
        })}
      />,
    );
    expect(screen.queryByTestId('patient-zero-env')).toBeNull();
  });

  // ── Owner line ───────────────────────────────────────────────────

  it('renders owner line when service is in the map', () => {
    render(
      <PatientZeroMetadata findings={findings({ patient_zero: pz('checkout-service') })} />,
    );
    expect(screen.getByTestId('patient-zero-owner')).toHaveTextContent(
      /owned by payments-platform/i,
    );
  });

  it('owner name is a Slack link when channel configured', () => {
    render(
      <PatientZeroMetadata findings={findings({ patient_zero: pz('checkout-service') })} />,
    );
    const link = screen.getByRole('link', { name: /payments-platform/i });
    expect(link.getAttribute('href')).toMatch(/slack\.com\/app_redirect/);
    expect(link.getAttribute('href')).toMatch(/channel=team-payments/);
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('owner line drops when service is not in the map', () => {
    render(
      <PatientZeroMetadata findings={findings({ patient_zero: pz('not-a-known-service') })} />,
    );
    expect(screen.queryByTestId('patient-zero-owner')).toBeNull();
  });

  it('normalises service casing when looking up owner', () => {
    render(
      <PatientZeroMetadata findings={findings({ patient_zero: pz('Checkout-SERVICE') })} />,
    );
    expect(screen.getByTestId('patient-zero-owner')).toHaveTextContent(/payments-platform/);
  });

  // ── Composition ──────────────────────────────────────────────────

  it('renders both lines when both data sources present', () => {
    render(
      <PatientZeroMetadata
        findings={findings({
          patient_zero: pz('checkout-service'),
          pod_statuses: [pod({ namespace: 'checkout-prod' })],
        })}
      />,
    );
    expect(screen.getByTestId('patient-zero-env')).toBeInTheDocument();
    expect(screen.getByTestId('patient-zero-owner')).toBeInTheDocument();
  });

  // ── Anti-pattern guards ──────────────────────────────────────────

  it('is not a card — no border, no rounded, no bg fill', () => {
    render(
      <PatientZeroMetadata
        findings={findings({
          patient_zero: pz('checkout-service'),
          pod_statuses: [pod({ namespace: 'x' })],
        })}
      />,
    );
    const meta = screen.getByTestId('patient-zero-metadata');
    expect(meta.className).not.toMatch(/rounded-/);
    expect(meta.className).not.toMatch(/border-/);
    expect(meta.className).not.toMatch(/bg-/);
  });

  it('no cyan and no amber in output', () => {
    render(
      <PatientZeroMetadata
        findings={findings({
          patient_zero: pz('checkout-service'),
          pod_statuses: [pod({ namespace: 'x' })],
        })}
      />,
    );
    const html = screen.getByTestId('patient-zero-metadata').innerHTML;
    expect(html).not.toMatch(/cyan/);
    expect(html).not.toMatch(/amber/);
    expect(html).not.toMatch(/wr-accent-2/);
  });
});
