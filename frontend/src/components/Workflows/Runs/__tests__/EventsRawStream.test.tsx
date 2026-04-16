import { describe, expect, test } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EventsRawStream } from '../EventsRawStream';
import type { LiveEvent } from '../StepStatusPanel';

const makeEvent = (overrides: Partial<LiveEvent> = {}): LiveEvent => ({
  id: 1,
  type: 'step.started',
  data: { node_id: 'n1', step_id: 's1' },
  timestamp: '2026-04-17T10:00:00Z',
  ...overrides,
});

describe('EventsRawStream', () => {
  test('renders "No events yet" when events array is empty', () => {
    render(<EventsRawStream events={[]} />);
    expect(screen.getByText('No events yet')).toBeInTheDocument();
  });

  test('renders event entries as JSON-serialized text', () => {
    const events: LiveEvent[] = [
      makeEvent({ id: 1, type: 'step.started' }),
      makeEvent({ id: 2, type: 'step.completed' }),
    ];
    render(<EventsRawStream events={events} />);

    expect(screen.queryByText('No events yet')).not.toBeInTheDocument();

    // Each event is rendered as JSON.stringify(evt)
    expect(screen.getByText(JSON.stringify(events[0]))).toBeInTheDocument();
    expect(screen.getByText(JSON.stringify(events[1]))).toBeInTheDocument();
  });

  test('renders the data-testid container', () => {
    render(<EventsRawStream events={[]} />);
    expect(screen.getByTestId('events-raw-stream')).toBeInTheDocument();
  });

  test('shows event data fields in the serialized output', () => {
    const evt = makeEvent({
      id: 3,
      type: 'step.failed',
      data: { node_id: 'n1', error: { type: 'RuntimeError', message: 'boom' } },
    });
    render(<EventsRawStream events={[evt]} />);

    const serialized = screen.getByText(JSON.stringify(evt));
    expect(serialized).toBeInTheDocument();
    // Verify the error details are present in the text
    expect(serialized.textContent).toContain('RuntimeError');
    expect(serialized.textContent).toContain('boom');
  });
});
