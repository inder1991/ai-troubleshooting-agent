import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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
        { id: 'step-b', agent: 'agent-b', agentVersion: 1, status: 'pending', x: 0, y: 160, width: 200, height: 80 },
      ],
      edges: [
        { source: 'step-a', target: 'step-b', points: [{ x: 100, y: 80 }, { x: 100, y: 160 }] },
      ],
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
import { StepStatusPanel } from '../StepStatusPanel';
import { ToastProvider } from '../../Shared/Toast';

function renderPage() {
  // Start in graph mode via localStorage
  localStorageMock.setItem('wf-run-view-mode', 'graph');
  return render(
    <ToastProvider>
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/workflows/runs/run-42',
            state: { workflowId: 'wf-1' },
          },
        ]}
      >
        <Routes>
          <Route path="/workflows/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

beforeEach(() => {
  MockEventSource.instances = [];
  mockGetRun.mockReset();
  mockCancelRun.mockReset();
  mockSubscribeEvents.mockReset();
  mockGetVersion.mockReset();
  localStorageMock.clear();

  mockGetRun.mockResolvedValue(FAKE_RUN);
  mockSubscribeEvents.mockImplementation((runId: string) => {
    return new MockEventSource(`/api/v4/runs/${runId}/events`);
  });
  mockGetVersion.mockResolvedValue(FAKE_VERSION);
});

afterEach(() => {
  MockEventSource.instances.forEach((es) => es.close());
  localStorageMock.clear();
});

describe('Bidirectional node-card highlighting', () => {
  test('click DagNode -> StepCard gets highlight ring class', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('dag-view-container')).toBeInTheDocument();
    });

    // Click on dag-node-step-a
    const dagNodeG = screen.getByTestId('dag-node-step-a');
    fireEvent.click(dagNodeG);

    // StepCard for step-a should get ring highlight
    await waitFor(() => {
      const stepCard = screen.getByTestId('step-card-step-a');
      expect(stepCard.className).toContain('ring-2');
      expect(stepCard.className).toContain('ring-wr-accent');
    });
  });

  test('click StepCard -> DagNode gets selected styling (accent stroke)', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('dag-view-container')).toBeInTheDocument();
    });

    // Click the step card for step-b
    const stepCard = screen.getByTestId('step-card-step-b');
    fireEvent.click(stepCard);

    // DagNode for step-b should get accent stroke (selected)
    await waitFor(() => {
      const dagNodeG = screen.getByTestId('dag-node-step-b');
      const rect = dagNodeG.querySelector('rect');
      expect(rect?.getAttribute('stroke')).toBe('#e09f3e');
    });
  });

  test('click same node/card again -> highlight clears', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('dag-view-container')).toBeInTheDocument();
    });

    // Click dag-node-step-a to highlight
    const dagNodeG = screen.getByTestId('dag-node-step-a');
    fireEvent.click(dagNodeG);

    await waitFor(() => {
      const stepCard = screen.getByTestId('step-card-step-a');
      expect(stepCard.className).toContain('ring-2');
    });

    // Click again to toggle off
    fireEvent.click(dagNodeG);

    await waitFor(() => {
      const stepCard = screen.getByTestId('step-card-step-a');
      expect(stepCard.className).not.toContain('ring-2');
    });
  });

  test('StepStatusPanel renders without highlighting props (backwards compatible)', () => {
    // Render StepStatusPanel standalone without highlight props
    render(
      <StepStatusPanel
        stepRuns={FAKE_RUN.step_runs}
      />,
    );

    expect(screen.getByText('step-a')).toBeInTheDocument();
    expect(screen.getByText('step-b')).toBeInTheDocument();

    // Cards should not have ring classes
    const cardA = screen.getByTestId('step-card-step-a');
    expect(cardA.className).not.toContain('ring-2');
    expect(cardA.className).not.toContain('cursor-pointer');
  });
});
