import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useRunEvents } from '../useRunEvents';

// ---- MockEventSource ----
class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onopen: ((e: Event) => void) | null = null;
  readyState = 0;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.(new Event('open'));
    }, 0);
  }

  close() {
    this.readyState = 2;
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }));
  }
}

// Assign globally
(globalThis as any).EventSource = MockEventSource;

// ---- Mock services/runs ----
const mockGetRun = vi.fn();
const mockSubscribeEvents = vi.fn();

vi.mock('../../../../services/runs', () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  subscribeEvents: (...args: unknown[]) => mockSubscribeEvents(...args),
  cancelRun: vi.fn(),
  RunTerminalError: class extends Error { constructor(s: string) { super(s); } },
}));

const FAKE_RUN = {
  id: 'run-1',
  workflow_version_id: 'wv-1',
  status: 'running' as const,
  inputs: {},
  step_runs: [
    { id: 'sr-1', step_id: 'step-a', status: 'pending' as const, attempt: 1 },
  ],
};

beforeEach(() => {
  MockEventSource.instances = [];
  mockGetRun.mockReset();
  mockSubscribeEvents.mockReset();
  mockGetRun.mockResolvedValue(FAKE_RUN);
  mockSubscribeEvents.mockImplementation((runId: string) => {
    return new MockEventSource(`/api/v4/runs/${runId}/events`);
  });
});

afterEach(() => {
  MockEventSource.instances.forEach((es) => es.close());
});

describe('useRunEvents', () => {
  test('fetches initial run on mount', async () => {
    const { result } = renderHook(() => useRunEvents('run-1'));

    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(mockGetRun).toHaveBeenCalledWith('run-1');
    expect(result.current.run?.id).toBe('run-1');
    expect(result.current.loading).toBe(false);
  });

  test('SSE message appended to liveEvents', async () => {
    const { result } = renderHook(() => useRunEvents('run-1'));

    await waitFor(() => expect(result.current.run).not.toBeNull());

    // Wait for EventSource to be created
    await waitFor(() => expect(MockEventSource.instances.length).toBeGreaterThan(0));

    const es = MockEventSource.instances[MockEventSource.instances.length - 1];

    act(() => {
      es.simulateMessage({
        id: 1,
        type: 'step.started',
        data: { step_id: 'step-a', status: 'running' },
        timestamp: new Date().toISOString(),
      });
    });

    expect(result.current.liveEvents).toHaveLength(1);
    expect(result.current.liveEvents[0].type).toBe('step.started');
  });

  test('terminal event closes EventSource', async () => {
    const { result } = renderHook(() => useRunEvents('run-1'));

    await waitFor(() => expect(result.current.run).not.toBeNull());
    await waitFor(() => expect(MockEventSource.instances.length).toBeGreaterThan(0));

    const es = MockEventSource.instances[MockEventSource.instances.length - 1];

    act(() => {
      es.simulateMessage({
        id: 2,
        type: 'run.completed',
        data: { status: 'success' },
        timestamp: new Date().toISOString(),
      });
    });

    expect(es.readyState).toBe(2); // closed
    expect(result.current.run?.status).toBe('success');
  });

  test('unmount closes EventSource', async () => {
    const { result, unmount } = renderHook(() => useRunEvents('run-1'));

    await waitFor(() => expect(result.current.run).not.toBeNull());
    await waitFor(() => expect(MockEventSource.instances.length).toBeGreaterThan(0));

    const es = MockEventSource.instances[MockEventSource.instances.length - 1];
    expect(es.readyState).not.toBe(2);

    unmount();

    expect(es.readyState).toBe(2);
  });
});
