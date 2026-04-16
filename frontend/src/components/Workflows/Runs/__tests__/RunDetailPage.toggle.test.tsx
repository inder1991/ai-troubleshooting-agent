import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { RunDetail, WorkflowVersionDetail, StepSpec } from '../../../../types';

// ---- Mock localStorage ----
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

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
}

(globalThis as any).EventSource = MockEventSource;

// ---- Mocks ----
const mockGetRun = vi.fn();
const mockCancelRun = vi.fn();
const mockSubscribeEvents = vi.fn();
const mockGetVersion = vi.fn();

vi.mock('../../../../services/runs', () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  cancelRun: (...args: unknown[]) => mockCancelRun(...args),
  subscribeEvents: (...args: unknown[]) => mockSubscribeEvents(...args),
  RunTerminalError: class extends Error {
    status: string;
    constructor(s: string) {
      super(`run already terminal: ${s}`);
      this.name = 'RunTerminalError';
      this.status = s;
    }
  },
}));

vi.mock('../../../../services/workflows', () => ({
  getVersion: (...args: unknown[]) => mockGetVersion(...args),
}));

// Mock useElkLayout to avoid elkjs WASM
vi.mock('../DagView/useElkLayout', () => ({
  useElkLayout: () => ({
    layout: {
      nodes: [
        { id: 'step-a', agent: 'agent-a', agentVersion: 1, status: 'running', x: 0, y: 0, width: 200, height: 80 },
      ],
      edges: [],
      width: 400,
      height: 320,
    },
    loading: false,
    error: null,
  }),
}));

const FAKE_RUN: RunDetail = {
  id: 'run-42',
  workflow_version_id: 'wv-1',
  status: 'running',
  inputs: {},
  step_runs: [
    { id: 'sr-1', step_id: 'step-a', status: 'running', attempt: 1 },
    { id: 'sr-2', step_id: 'step-b', status: 'pending', attempt: 1 },
  ],
};

const FAKE_STEPS: StepSpec[] = [
  { id: 'step-a', agent: 'agent-a', agent_version: 1, inputs: {} },
  { id: 'step-b', agent: 'agent-b', agent_version: 1, inputs: {}, depends_on: ['step-a'] },
];

const FAKE_VERSION: WorkflowVersionDetail = {
  workflow_id: 'wf-1',
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  dag: { inputs_schema: {}, steps: FAKE_STEPS },
};

// Import after mocks
import { RunDetailPage } from '../RunDetailPage';

function renderPage(opts: { locationState?: Record<string, unknown>; initialLocalStorage?: string } = {}) {
  if (opts.initialLocalStorage) {
    window.localStorage.setItem('wf-run-view-mode', opts.initialLocalStorage);
  }
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: '/workflows/runs/run-42',
          state: opts.locationState,
        },
      ]}
    >
      <Routes>
        <Route path="/workflows/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  MockEventSource.instances = [];
  mockGetRun.mockReset();
  mockCancelRun.mockReset();
  mockSubscribeEvents.mockReset();
  mockGetVersion.mockReset();
  window.localStorage.clear();

  mockGetRun.mockResolvedValue(FAKE_RUN);
  mockSubscribeEvents.mockImplementation((runId: string) => {
    return new MockEventSource(`/api/v4/runs/${runId}/events`);
  });
  mockGetVersion.mockResolvedValue(FAKE_VERSION);
});

afterEach(() => {
  MockEventSource.instances.forEach((es) => es.close());
  window.localStorage.clear();
});

describe('RunDetailPage toggle', () => {
  test('default: cards view rendered, no DagView container', async () => {
    renderPage({ locationState: { workflowId: 'wf-1' } });

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    // Cards toggle is active
    const cardsBtn = screen.getByTestId('view-toggle-cards');
    expect(cardsBtn.className).toContain('bg-wr-accent');

    // DagView container should NOT be present
    expect(screen.queryByTestId('dag-view-container')).not.toBeInTheDocument();
  });

  test('toggle to Graph: DagView container rendered', async () => {
    const user = userEvent.setup();
    renderPage({ locationState: { workflowId: 'wf-1' } });

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const graphBtn = screen.getByTestId('view-toggle-graph');
    await user.click(graphBtn);

    // DagView should now render
    await waitFor(() => {
      expect(screen.getByTestId('dag-view-container')).toBeInTheDocument();
    });

    // Graph toggle is now active
    expect(graphBtn.className).toContain('bg-wr-accent');
  });

  test('toggle persists to localStorage', async () => {
    const user = userEvent.setup();
    renderPage({ locationState: { workflowId: 'wf-1' } });

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const graphBtn = screen.getByTestId('view-toggle-graph');
    await user.click(graphBtn);

    expect(window.localStorage.getItem('wf-run-view-mode')).toBe('graph');

    // Toggle back to cards
    const cardsBtn = screen.getByTestId('view-toggle-cards');
    await user.click(cardsBtn);

    expect(window.localStorage.getItem('wf-run-view-mode')).toBe('cards');
  });

  test('page load with localStorage graph -> Graph view rendered', async () => {
    renderPage({ locationState: { workflowId: 'wf-1' }, initialLocalStorage: 'graph' });

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    // DagView should render because localStorage had 'graph'
    await waitFor(() => {
      expect(screen.getByTestId('dag-view-container')).toBeInTheDocument();
    });

    const graphBtn = screen.getByTestId('view-toggle-graph');
    expect(graphBtn.className).toContain('bg-wr-accent');
  });

  test('graph toggle disabled when no workflowId in location state', async () => {
    renderPage(); // no locationState

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const graphBtn = screen.getByTestId('view-toggle-graph');
    expect(graphBtn).toBeDisabled();
    expect(graphBtn.getAttribute('title')).toContain('Navigate from a workflow');
  });
});
