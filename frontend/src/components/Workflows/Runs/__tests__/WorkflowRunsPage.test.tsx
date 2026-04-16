import { describe, expect, test, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { WorkflowRunsPage } from '../WorkflowRunsPage';
import { ToastProvider } from '../../Shared/Toast';
import type { RunStatus } from '../../../../types';

// ---- Mock data ----

const mockRunsResponse = {
  runs: [
    {
      id: 'run-1',
      workflow_version_id: 'wv-1',
      status: 'success' as RunStatus,
      started_at: new Date(Date.now() - 120_000).toISOString(),
    },
    {
      id: 'run-2',
      workflow_version_id: 'wv-2',
      status: 'running' as RunStatus,
      started_at: new Date(Date.now() - 600_000).toISOString(),
    },
    {
      id: 'run-3',
      workflow_version_id: 'wv-1',
      status: 'failed' as RunStatus,
      started_at: new Date(Date.now() - 3600_000).toISOString(),
    },
  ],
  total: 3,
  limit: 50,
  offset: 0,
};

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
  // listRuns
  http.get('/api/v4/runs', () =>
    HttpResponse.json(mockRunsResponse),
  ),
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
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---- Helper ----

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage(initialPath = '/workflows/runs') {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/workflows/runs" element={<WorkflowRunsPage />} />
          <Route path="/workflows/runs/:runId" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

// ---- Tests ----

describe('WorkflowRunsPage', () => {
  test('renders empty state when API returns no runs', async () => {
    server.use(
      http.get('/api/v4/runs', () =>
        HttpResponse.json({ runs: [], total: 0, limit: 50, offset: 0 }),
      ),
    );
    renderPage();
    expect(
      await screen.findByText(/no runs found/i),
    ).toBeInTheDocument();
  });

  test('renders run entries from API', async () => {
    renderPage();

    // Should show run IDs
    expect(await screen.findByText(/run-1/)).toBeInTheDocument();
    expect(screen.getByText(/run-2/)).toBeInTheDocument();
    expect(screen.getByText(/run-3/)).toBeInTheDocument();
  });

  test('click View navigates to /workflows/runs/:runId', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v4/runs', () =>
        HttpResponse.json({
          runs: [mockRunsResponse.runs[0]],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderPage();

    const viewBtn = await screen.findByRole('link', { name: /view/i });
    await user.click(viewBtn);

    expect(await screen.findByTestId('location')).toHaveTextContent(
      '/workflows/runs/run-1',
    );
  });

  test('status badge shows correct color for each status', async () => {
    const statuses: RunStatus[] = ['pending', 'running', 'success', 'failed', 'cancelled', 'cancelling'];
    server.use(
      http.get('/api/v4/runs', () =>
        HttpResponse.json({
          runs: statuses.map((status, i) => ({
            id: `run-${status}`,
            workflow_version_id: 'wv-1',
            status,
            started_at: new Date(Date.now() - i * 60_000).toISOString(),
          })),
          total: statuses.length,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderPage();

    // Wait for page to render
    expect(await screen.findByText('run-pending')).toBeInTheDocument();

    const badges = screen.getAllByTestId('run-status-badge');
    const badgeMap = new Map(
      badges.map((b) => [b.textContent, b.className]),
    );

    expect(badgeMap.get('running')).toContain('amber');
    expect(badgeMap.get('success')).toContain('emerald');
    expect(badgeMap.get('failed')).toContain('red');
    expect(badgeMap.get('cancelled')).toContain('slate');
    expect(badgeMap.get('pending')).toContain('neutral');
  });

  test('new run flow: select workflow, version, fill form, submit, createRun called', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for runs to load first
    await screen.findByText(/run-1/);

    // Click "New run" button
    const newRunBtn = screen.getByRole('button', { name: /new run/i });
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
  });

  test('does not show localStorage footer note', async () => {
    renderPage();
    await screen.findByText(/run-1/);
    expect(
      screen.queryByText(/showing runs from this browser only/i),
    ).not.toBeInTheDocument();
  });

  test('shows filter bar', async () => {
    renderPage();
    await screen.findByText(/run-1/);
    expect(screen.getByLabelText(/sort/i)).toBeInTheDocument();
  });
});
