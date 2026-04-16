import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { RunDetailPage } from '../RunDetailPage';
import { ToastProvider } from '../../Shared/Toast';
import type { RunDetail } from '../../../../types';

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

(globalThis as any).EventSource = MockEventSource;

// ---- Mocks ----
const mockGetRun = vi.fn();
const mockCancelRun = vi.fn();
const mockSubscribeEvents = vi.fn();
const mockCreateRun = vi.fn();
const mockGetRerunData = vi.fn();

vi.mock('../../../../services/runs', () => ({
  getRun: (...args: unknown[]) => mockGetRun(...args),
  cancelRun: (...args: unknown[]) => mockCancelRun(...args),
  createRun: (...args: unknown[]) => mockCreateRun(...args),
  getRerunData: (...args: unknown[]) => mockGetRerunData(...args),
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

const mockGetVersion = vi.fn();

vi.mock('../../../../services/workflows', () => ({
  getVersion: (...args: unknown[]) => mockGetVersion(...args),
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

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/workflows/runs/run-42']}>
        <Routes>
          <Route path="/workflows/runs/:runId" element={<RunDetailPage />} />
          <Route path="/workflows/runs/:runId/nav" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

beforeEach(() => {
  MockEventSource.instances = [];
  mockGetRun.mockReset();
  mockCancelRun.mockReset();
  mockCreateRun.mockReset();
  mockGetRerunData.mockReset();
  mockGetVersion.mockReset();
  mockSubscribeEvents.mockReset();
  mockGetRun.mockResolvedValue(FAKE_RUN);
  mockGetVersion.mockResolvedValue({ dag: { steps: [], inputs_schema: {} } });
  mockSubscribeEvents.mockImplementation((runId: string) => {
    return new MockEventSource(`/api/v4/runs/${runId}/events`);
  });
});

afterEach(() => {
  MockEventSource.instances.forEach((es) => es.close());
});

describe('RunDetailPage', () => {
  test('renders run header with status badge', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });
    // Status badge
    expect(screen.getByTestId('run-status-badge')).toHaveTextContent('running');
  });

  test('StepStatusPanel rendered with step_runs', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });
    expect(screen.getByText('step-b')).toBeInTheDocument();
  });

  test('cancel button calls cancelRun', async () => {
    const user = userEvent.setup();
    mockCancelRun.mockResolvedValue({ ...FAKE_RUN, status: 'cancelled' });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelBtn);

    expect(mockCancelRun).toHaveBeenCalledWith('run-42');
  });

  test('"Show raw events" toggle reveals EventsRawStream', async () => {
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    // Raw events section not visible initially
    expect(screen.queryByTestId('events-raw-stream')).not.toBeInTheDocument();

    const toggleBtn = screen.getByRole('button', { name: /show raw events/i });
    await user.click(toggleBtn);

    expect(screen.getByTestId('events-raw-stream')).toBeInTheDocument();
  });

  // ---- Rerun tests ----

  test('rerun button is disabled while run is still running', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const rerunBtn = screen.getByRole('button', { name: /^rerun$/i });
    expect(rerunBtn).toBeDisabled();
  });

  test('rerun button is enabled for terminal run and calls createRun', async () => {
    const user = userEvent.setup();

    const terminalRun: RunDetail = {
      ...FAKE_RUN,
      status: 'success',
      workflow_id: 'wf-abc',
      step_runs: [
        { id: 'sr-1', step_id: 'step-a', status: 'success', attempt: 1 },
      ],
    };
    mockGetRun.mockResolvedValue(terminalRun);
    mockGetRerunData.mockResolvedValue({
      workflow_version_id: 'wv-1',
      inputs: { service: 'api' },
    });
    mockCreateRun.mockResolvedValue({
      id: 'run-99',
      workflow_version_id: 'wv-1',
      status: 'pending',
      inputs: { service: 'api' },
      step_runs: [],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const rerunBtn = screen.getByRole('button', { name: /^rerun$/i });
    expect(rerunBtn).toBeEnabled();

    await user.click(rerunBtn);

    await waitFor(() => {
      expect(mockGetRerunData).toHaveBeenCalledWith('run-42');
    });
    expect(mockCreateRun).toHaveBeenCalledWith('wf-abc', { inputs: { service: 'api' } });
  });

  test('rerun failure shows error toast', async () => {
    const user = userEvent.setup();

    const terminalRun: RunDetail = {
      ...FAKE_RUN,
      status: 'failed',
      workflow_id: 'wf-abc',
      step_runs: [],
    };
    mockGetRun.mockResolvedValue(terminalRun);
    mockGetRerunData.mockRejectedValue(new Error('Server error'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/run-42/i)).toBeInTheDocument();
    });

    const rerunBtn = screen.getByRole('button', { name: /^rerun$/i });
    await user.click(rerunBtn);

    // getErrorMessage returns the Error.message, which is 'Server error'
    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });
});
