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

  // ---- Filter tests ----

  test('clicking a status chip updates URL search params and refetches', async () => {
    const user = userEvent.setup();
    let capturedUrl = '';

    server.use(
      http.get('/api/v4/runs', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(mockRunsResponse);
      }),
    );

    renderPage();
    await screen.findByText(/run-1/);

    // Click "Failed" status chip
    await user.click(screen.getByRole('button', { name: /^failed$/i }));

    // Wait for refetch with status param
    await waitFor(() => {
      expect(capturedUrl).toContain('status=failed');
    });
  });

  test('clicking multiple status chips combines them in URL', async () => {
    const user = userEvent.setup();
    let capturedUrl = '';

    server.use(
      http.get('/api/v4/runs', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(mockRunsResponse);
      }),
    );

    renderPage();
    await screen.findByText(/run-1/);

    // Click "Failed" then "Running"
    await user.click(screen.getByRole('button', { name: /^failed$/i }));
    await waitFor(() => {
      expect(capturedUrl).toContain('status=failed');
    });

    await user.click(screen.getByRole('button', { name: /^running$/i }));
    await waitFor(() => {
      expect(capturedUrl).toContain('status=failed%2Crunning');
    });
  });

  test('toggling a status chip off removes it from URL', async () => {
    const user = userEvent.setup();
    let capturedUrl = '';

    server.use(
      http.get('/api/v4/runs', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(mockRunsResponse);
      }),
    );

    renderPage();
    await screen.findByText(/run-1/);

    // Click "Failed" to enable
    await user.click(screen.getByRole('button', { name: /^failed$/i }));
    await waitFor(() => {
      expect(capturedUrl).toContain('status=failed');
    });

    // Click "Failed" again to disable
    await user.click(screen.getByRole('button', { name: /^failed$/i }));
    await waitFor(() => {
      expect(capturedUrl).not.toContain('status=');
    });
  });

  // ---- Pagination tests ----

  test('pagination controls appear when total > LIMIT and navigate pages', async () => {
    const user = userEvent.setup();
    const requests: string[] = [];

    // 60 total runs with limit 50 means pagination should show
    server.use(
      http.get('/api/v4/runs', ({ request }) => {
        requests.push(request.url);
        const url = new URL(request.url);
        const offset = Number(url.searchParams.get('offset') ?? '0');
        return HttpResponse.json({
          runs: offset === 0
            ? mockRunsResponse.runs
            : [{ id: 'run-page2', workflow_version_id: 'wv-1', status: 'success' as RunStatus, started_at: new Date().toISOString() }],
          total: 60,
          limit: 50,
          offset,
        });
      }),
    );

    renderPage();
    await screen.findByText(/run-1/);

    // Pagination should show
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();

    // Click Next
    await user.click(screen.getByRole('button', { name: /next/i }));

    // Should fetch with offset=50 (page 1 * LIMIT 50)
    await waitFor(() => {
      const lastReq = requests[requests.length - 1];
      expect(lastReq).toContain('offset=50');
    });

    // Wait for page 2 data
    await screen.findByText('run-page2');

    // Next should be disabled on last page, Previous enabled
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled();

    // Click Previous
    await user.click(screen.getByRole('button', { name: /previous/i }));

    // Should refetch with offset=0
    await waitFor(() => {
      const lastReq = requests[requests.length - 1];
      expect(lastReq).toContain('offset=0');
    });
  });

  test('pagination is not shown when total <= LIMIT', async () => {
    renderPage();
    await screen.findByText(/run-1/);

    // Default mock has total=3, limit=50 — no pagination
    expect(screen.queryByRole('button', { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /next/i })).not.toBeInTheDocument();
  });
});
