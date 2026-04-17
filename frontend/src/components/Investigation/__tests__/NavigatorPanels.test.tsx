import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { InfraPills } from '../InfraPills';
import { AgentCircuitIndicator } from '../AgentCircuitIndicator';
import { MetricEntry } from '../MetricEntry';

describe('InfraPills', () => {
  it('shows MemoryPressure for affected nodes', () => {
    render(
      <InfraPills
        nodeConditions={[
          { node: 'node-3', type: 'MemoryPressure', status: 'True' },
        ]}
        pvcPending={2}
        pdbViolations={1}
        hpaSaturated={['api-hpa']}
      />,
    );
    expect(screen.getByText(/MemoryPressure · node-3/)).toBeInTheDocument();
    expect(screen.getByText(/PVC pending: 2/)).toBeInTheDocument();
    expect(screen.getByText(/PDB violations: 1/)).toBeInTheDocument();
    expect(screen.getByText(/HPA saturated · api-hpa/)).toBeInTheDocument();
  });

  it('filters node conditions to only status="True"', () => {
    render(
      <InfraPills
        nodeConditions={[
          { node: 'node-1', type: 'Ready', status: 'True' },
          { node: 'node-2', type: 'MemoryPressure', status: 'False' },
        ]}
      />,
    );
    expect(screen.queryByText(/MemoryPressure/)).toBeNull();
    // "Ready" with status=True is rendered but color tone isn't asserted here
    expect(screen.getByText(/Ready · node-1/)).toBeInTheDocument();
  });

  it('returns null when nothing to show', () => {
    const { container } = render(<InfraPills />);
    expect(container.firstChild).toBeNull();
  });
});

describe('AgentCircuitIndicator', () => {
  it('renders OPEN state in red', () => {
    render(<AgentCircuitIndicator agent="metrics_agent" state="open" />);
    const el = screen.getByTestId('breaker-metrics_agent');
    expect(el.className).toMatch(/wr-red|text-red/);
  });

  it('renders CLOSED state in emerald', () => {
    render(<AgentCircuitIndicator agent="metrics_agent" state="closed" />);
    const el = screen.getByTestId('breaker-metrics_agent');
    expect(el.className).toMatch(/wr-emerald|emerald/);
    expect(el.className).not.toMatch(/wr-red/);
  });

  it('renders HALF_OPEN in amber', () => {
    render(<AgentCircuitIndicator agent="metrics_agent" state="half_open" />);
    const el = screen.getByTestId('breaker-metrics_agent');
    expect(el.className).toMatch(/wr-amber|amber/);
  });
});

describe('MetricEntry', () => {
  it('shows baseline strip when delta present', () => {
    render(
      <MetricEntry name="cpu" value={82} baselineValue={80} baselineDeltaPct={2.5} />,
    );
    expect(screen.getByText(/within 2\.5% of 24h baseline/i)).toBeInTheDocument();
  });

  it('renders just name+value when baseline absent', () => {
    render(<MetricEntry name="rps" value={1200} />);
    expect(screen.queryByTestId('baseline-strip-rps')).toBeNull();
    expect(screen.getByText('rps')).toBeInTheDocument();
    expect(screen.getByText('1200')).toBeInTheDocument();
  });

  it('baseline tone is red at >= 50% delta', () => {
    render(
      <MetricEntry name="err" value={10} baselineValue={1} baselineDeltaPct={900} />,
    );
    const strip = screen.getByTestId('baseline-strip-err');
    expect(strip.className).toMatch(/wr-red/);
  });

  it('baseline tone is amber at 15-49% delta', () => {
    render(
      <MetricEntry name="latency" value={250} baselineValue={200} baselineDeltaPct={25} />,
    );
    const strip = screen.getByTestId('baseline-strip-latency');
    expect(strip.className).toMatch(/wr-amber/);
  });
});
