import { describe, expect, test, vi, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { WorkflowRunsPage } from '../WorkflowRunsPage';
import type { RecentRunEntry } from '../recentRuns';
import type { RunStatus } from '../../../../types';

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

// ---- Constants ----

const STORAGE_KEY = 'wf-recent-runs';

// ---- Mock data ----

const mockRuns: RecentRunEntry[] = [
  {
    runId: 'run-1',
    workflowId: 'wf-1',
    workflowName: 'Log Analysis Pipeline',
    status: 'succeeded',
    startedAt: new Date(Date.now() - 120_000).toISOString(), // 2 min ago
  },
  {
    runId: 'run-2',
    workflowId: 'wf-2',
    workflowName: 'Code Review Bot',
    status: 'running',
    startedAt: new Date(Date.now() - 600_000).toISOString(), // 10 min ago
  },
  {
    runId: 'run-3',
    workflowId: 'wf-1',
    workflowName: 'Log Analysis Pipeline',
    status: 'failed',
    startedAt: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
  },
];

const mockWorkflows = [
  { id: 'wf-1', name: 'Log Analysis Pipeline', description: 'desc1', created_at: '2026-01-01T00:00:00Z' },
  { id: 'wf-2', name: 'Code Review Bot', description: 'desc2', created_at: '2026-01-02T00:00:00Z' },
];

const mockVersions = [
  { version_id: 'v-1', workflow_id: 'wf-1', version: 1, created_at: '2026-01-01T00:00:00Z' },
  { version_id: 'v-2', workflow_id: 'wf-1', version: 2, created_at: '2026-01-02T00:00:00Z' },
];

const mockVersionDetail = {
  workflow_id: 'wf-1',
  version: 2,
  created_at: '2026-01-02T00:00:00Z',
  dag: {
    inputs_schema: {
      type: 'object',
      properties: { service: { type: 'string', default: 'api' } },
    },
    steps: [],
  },
  compiled: null,
};

// ---- MSW Server ----

const server = setupServer(
  // getRun - refresh status
  http.get('/api/v4/runs/:runId', ({ params }) => {
    const entry = mockRuns.find((r) => r.runId === params.runId);
    if (!entry) return HttpResponse.json({}, { status: 404 });
    return HttpResponse.json({
      run: {
        id: entry.runId,
        workflow_version_id: 'wv-1',
        status: entry.status,
        started_at: entry.startedAt,
        inputs: {},
      },
      step_runs: [],
    });
  }),
  // listWorkflows
  http.get('/api/v4/workflows', () =>
    HttpResponse.json({ workflows: mockWorkflows }),
  ),
  // listVersions
  http.get('/api/v4/workflows/:wfId/versions', () =>
    HttpResponse.json({ versions: mockVersions }),
  ),
  // getVersion
  http.get('/api/v4/workflows/:wfId/versions/:v', () =>
    HttpResponse.json(mockVersionDetail),
  ),
  // createRun
  http.post('/api/v4/workflows/:wfId/runs', async () =>
    HttpResponse.json({
      run: {
        id: 'run-new',
        workflow_version_id: 'wv-1',
        status: 'pending',
        started_at: new Date().toISOString(),
        inputs: {},
      },
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  localStorageMock.clear();
});
afterAll(() => server.close());

// ---- Helper ----

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage(initialPath = '/workflows/runs') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/workflows/runs" element={<WorkflowRunsPage />} />
        <Route path="/workflows/runs/:runId" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---- Tests ----

describe('WorkflowRunsPage', () => {
  test('renders empty state when no recent runs in localStorage', async () => {
    renderPage();
    expect(
      await screen.findByText(/no recent runs/i),
    ).toBeInTheDocument();
  });

  test('renders run entries from localStorage', async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(mockRuns));
    renderPage();

    // Should show truncated run IDs
    expect(await screen.findByText(/run-1/)).toBeInTheDocument();
    expect(screen.getByText(/run-2/)).toBeInTheDocument();
    expect(screen.getByText(/run-3/)).toBeInTheDocument();

    // Should show workflow names
    expect(screen.getAllByText(/Log Analysis Pipeline/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Code Review Bot/)).toBeInTheDocument();
  });

  test('click View navigates to /workflows/runs/:runId', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([mockRuns[0]]));
    renderPage();

    const viewBtn = await screen.findByRole('link', { name: /view/i });
    await user.click(viewBtn);

    expect(await screen.findByTestId('location')).toHaveTextContent(
      '/workflows/runs/run-1',
    );
  });

  test('status badge shows correct color for each status', async () => {
    const statuses: RunStatus[] = ['pending', 'running', 'succeeded', 'failed', 'cancelled', 'cancelling'];
    const entries: RecentRunEntry[] = statuses.map((status, i) => ({
      runId: `run-${status}`,
      workflowId: 'wf-1',
      workflowName: 'W',
      status,
      startedAt: new Date(Date.now() - i * 60_000).toISOString(),
    }));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    renderPage();

    // Wait for page to render
    expect(await screen.findByText('run-pending')).toBeInTheDocument();

    const badges = screen.getAllByTestId('run-status-badge');
    const badgeMap = new Map(
      badges.map((b) => [b.textContent, b.className]),
    );

    expect(badgeMap.get('running')).toContain('amber');
    expect(badgeMap.get('succeeded')).toContain('emerald');
    expect(badgeMap.get('failed')).toContain('red');
    expect(badgeMap.get('cancelled')).toContain('slate');
    expect(badgeMap.get('pending')).toContain('neutral');
  });

  test('new run flow: select workflow, version, fill form, submit, createRun called', async () => {
    const user = userEvent.setup();
    renderPage();

    // Click "New run" button
    const newRunBtn = await screen.findByRole('button', { name: /new run/i });
    await user.click(newRunBtn);

    // Step 1: pick workflow
    const wfSelect = await screen.findByLabelText(/workflow/i);
    await user.selectOptions(wfSelect, 'wf-1');

    // Step 1b: pick version
    const versionSelect = await screen.findByLabelText(/version/i);
    await user.selectOptions(versionSelect, '2');

    // Step 2: InputsForm appears — click "Run workflow" button
    const runBtn = await screen.findByRole('button', { name: /run workflow/i });
    await user.click(runBtn);

    // Should navigate to the new run detail page
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/workflows/runs/run-new',
      );
    });

    // Verify the run was added to localStorage
    const stored = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? '[]',
    );
    expect(stored.some((e: RecentRunEntry) => e.runId === 'run-new')).toBe(true);
  });

  test('shows footer note about browser-only runs', async () => {
    renderPage();
    expect(
      await screen.findByText(/showing runs from this browser only/i),
    ).toBeInTheDocument();
  });
});
