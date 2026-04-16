import { describe, expect, test, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { WorkflowBuilderPage } from '../WorkflowBuilderPage';
import type {
  WorkflowDetail,
  VersionSummary,
  WorkflowVersionDetail,
  CatalogAgentSummary,
  WorkflowDag,
} from '../../../../types';

// ---- Mock data ----

const mockWorkflow: WorkflowDetail = {
  id: 'wf-1',
  name: 'Test Workflow',
  description: 'A test workflow',
  created_at: '2026-01-01T00:00:00Z',
  latest_version: { version: 2, created_at: '2026-02-01T00:00:00Z' },
};

const mockVersions: VersionSummary[] = [
  { version_id: 'v-1', workflow_id: 'wf-1', version: 1, created_at: '2026-01-01T00:00:00Z' },
  { version_id: 'v-2', workflow_id: 'wf-1', version: 2, created_at: '2026-02-01T00:00:00Z' },
];

const mockDag: WorkflowDag = {
  inputs_schema: {},
  steps: [
    { id: 'step-a', agent: 'log_analyzer', agent_version: 1, inputs: {} },
  ],
};

const mockVersionDetail: WorkflowVersionDetail = {
  workflow_id: 'wf-1',
  version: 2,
  created_at: '2026-02-01T00:00:00Z',
  dag: mockDag,
  compiled: null,
};

const mockVersion1Detail: WorkflowVersionDetail = {
  workflow_id: 'wf-1',
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  dag: { inputs_schema: {}, steps: [] },
  compiled: null,
};

const mockCatalog: CatalogAgentSummary[] = [
  { name: 'log_analyzer', version: 2, description: 'Analyzes logs', category: 'analysis', tags: ['logs'] },
  { name: 'code_navigator', version: 1, description: 'Navigates code', category: 'code', tags: ['code'] },
];

const mockAgentDetail = {
  name: 'log_analyzer',
  version: 2,
  description: 'Analyzes logs',
  category: 'analysis',
  tags: ['logs'],
  deprecated_versions: [],
  input_schema: { type: 'object', properties: { query: { type: 'string' } } },
  output_schema: { type: 'object', properties: {} },
  trigger_examples: [],
  timeout_seconds: 60,
  retry_on: [],
};

// ---- MSW Server ----

const server = setupServer(
  http.get('/api/v4/workflows/:id', () => HttpResponse.json(mockWorkflow)),
  http.get('/api/v4/workflows/:id/versions', () =>
    HttpResponse.json({ versions: mockVersions }),
  ),
  http.get('/api/v4/workflows/:id/versions/:version', ({ params }) => {
    const v = Number(params.version);
    if (v === 1) return HttpResponse.json(mockVersion1Detail);
    return HttpResponse.json(mockVersionDetail);
  }),
  http.get('/api/v4/catalog/agents', () =>
    HttpResponse.json({ agents: mockCatalog }),
  ),
  http.get('/api/v4/catalog/agents/:name/v/:version', () =>
    HttpResponse.json(mockAgentDetail),
  ),
  http.post('/api/v4/workflows/:id/versions', () =>
    HttpResponse.json({
      version_id: 'v-3',
      workflow_id: 'wf-1',
      version: 3,
      created_at: '2026-03-01T00:00:00Z',
    }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---- Helpers ----

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/workflows/wf-1']}>
      <Routes>
        <Route path="/workflows/:workflowId" element={<WorkflowBuilderPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---- Tests ----

describe('WorkflowBuilderPage', () => {
  test('renders header, step list, and validation banner', async () => {
    renderPage();

    // Workflow name appears in header
    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    // Step from loaded DAG visible (step id shown in StepSummaryRow)
    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // "Add step" button present
    expect(screen.getByRole('button', { name: /add step/i })).toBeInTheDocument();
  });

  test('"Add step" adds a step to the list', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    // Wait for DAG to load
    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Open add step dropdown
    await user.click(screen.getByRole('button', { name: /add step/i }));

    // Select code_navigator from dropdown
    await user.click(screen.getByText('code_navigator'));

    // Should now have 2 step rows
    await waitFor(() => {
      const rows = screen.getAllByTestId('step-row');
      expect(rows.length).toBe(2);
    });
  });

  test('clicking a step opens the drawer', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Click step-a (it's rendered as a button in StepSummaryRow)
    await user.click(screen.getByText('step-a'));

    // Drawer should appear
    await waitFor(() => {
      expect(screen.getByTestId('step-drawer')).toBeInTheDocument();
    });
  });

  test('removing a step from drawer removes it from list', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Click step to open drawer
    await user.click(screen.getByText('step-a'));

    await waitFor(() => {
      expect(screen.getByTestId('step-drawer')).toBeInTheDocument();
    });

    // StepDrawer has a delete button; click it then confirm
    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await user.click(deleteBtn);

    // Confirm prompt
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    await user.click(confirmBtn);

    // Step should be gone
    await waitFor(() => {
      expect(screen.queryByText('step-a')).not.toBeInTheDocument();
    });
  });

  test('save calls createVersion with current dag, success refreshes versions', async () => {
    const user = userEvent.setup();
    let createCalled = false;
    let postedDag: WorkflowDag | null = null;

    server.use(
      http.post('/api/v4/workflows/:id/versions', async ({ request }) => {
        createCalled = true;
        postedDag = (await request.json()) as WorkflowDag;
        return HttpResponse.json({
          version_id: 'v-3',
          workflow_id: 'wf-1',
          version: 3,
          created_at: '2026-03-01T00:00:00Z',
        });
      }),
      // After save, getVersion for v3 returns updated dag
      http.get('/api/v4/workflows/:id/versions/3', () =>
        HttpResponse.json({
          workflow_id: 'wf-1',
          version: 3,
          created_at: '2026-03-01T00:00:00Z',
          dag: mockDag,
          compiled: null,
        }),
      ),
      // Refreshed version list includes v3
      http.get('/api/v4/workflows/:id/versions', () =>
        HttpResponse.json({
          versions: [
            ...mockVersions,
            { version_id: 'v-3', workflow_id: 'wf-1', version: 3, created_at: '2026-03-01T00:00:00Z' },
          ],
        }),
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Make dirty by adding a step
    await user.click(screen.getByRole('button', { name: /add step/i }));
    await user.click(screen.getByText('code_navigator'));

    // Save
    const saveBtn = screen.getByRole('button', { name: /save as new version/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(createCalled).toBe(true);
    });
    expect(postedDag).not.toBeNull();
    expect(postedDag!.steps.length).toBe(2);

    // Success banner
    await waitFor(() => {
      expect(screen.getByText(/version saved/i)).toBeInTheDocument();
    });
  });

  test('save 422 CompileError shows errors in ValidationBanner', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Make dirty
    await user.click(screen.getByRole('button', { name: /add step/i }));
    await user.click(screen.getByText('code_navigator'));

    // Override to return 422
    server.use(
      http.post('/api/v4/workflows/:id/versions', () =>
        HttpResponse.json(
          {
            detail: {
              type: 'compile_error',
              message: 'Invalid step reference',
              path: 'steps[1].inputs',
              errors: [{ message: 'Invalid step reference' }],
            },
          },
          { status: 422 },
        ),
      ),
    );

    await user.click(screen.getByRole('button', { name: /save as new version/i }));

    // Validation banner appears (collapsed)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    // Expand it to see details
    const user2 = userEvent.setup();
    await user2.click(screen.getByText(/show details/i));

    expect(screen.getByText(/invalid step reference/i)).toBeInTheDocument();
  });

  test('version switch with dirty state shows confirm dialog', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('step-a')).toBeInTheDocument();
    });

    // Make dirty
    await user.click(screen.getByRole('button', { name: /add step/i }));
    await user.click(screen.getByText('code_navigator'));

    // Switch version: select v1 in dropdown then click View
    const versionSelect = screen.getByLabelText('Workflow version');
    await user.selectOptions(versionSelect, '1');

    const viewBtn = screen.getByRole('button', { name: /^view$/i });
    await user.click(viewBtn);

    // Confirm dialog
    await waitFor(() => {
      expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
    });

    // Click "Discard & switch"
    await user.click(screen.getByText(/discard/i));

    // Confirm dialog gone
    await waitFor(() => {
      expect(screen.queryByText(/unsaved changes/i)).not.toBeInTheDocument();
    });
  });

  test('clientErrors: duplicate step ids produce error', async () => {
    // Serve a DAG with duplicate step ids
    server.use(
      http.get('/api/v4/workflows/:id/versions/:version', () =>
        HttpResponse.json({
          workflow_id: 'wf-1',
          version: 2,
          created_at: '2026-02-01T00:00:00Z',
          dag: {
            inputs_schema: {},
            steps: [
              { id: 'dup-id', agent: 'log_analyzer', agent_version: 1, inputs: {} },
              { id: 'dup-id', agent: 'code_navigator', agent_version: 1, inputs: {} },
            ],
          },
          compiled: null,
        }),
      ),
    );

    renderPage();

    // Validation banner should show duplicate error (collapsed initially)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    // Expand to see details
    const user = userEvent.setup();
    await user.click(screen.getByText(/show details/i));

    expect(screen.getByText(/duplicate step id/i)).toBeInTheDocument();
  });

  // ---- Task 20: Run trigger wiring ----

  test('Run button opens InputsForm modal', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    // Click the Run button
    await user.click(screen.getByRole('button', { name: /^run$/i }));

    // InputsForm modal should appear
    await waitFor(() => {
      expect(screen.getByTestId('inputs-form-modal')).toBeInTheDocument();
    });
  });

  test('submit form -> createRun called -> navigates to run detail route', async () => {
    // Use a dag with simple inputs_schema so form mode is used
    const dagWithSchema: WorkflowDag = {
      inputs_schema: {
        type: 'object',
        properties: {
          query: { type: 'string' },
        },
      },
      steps: [
        { id: 'step-a', agent: 'log_analyzer', agent_version: 1, inputs: {} },
      ],
    };

    server.use(
      http.get('/api/v4/workflows/:id/versions/:version', () =>
        HttpResponse.json({
          workflow_id: 'wf-1',
          version: 2,
          created_at: '2026-02-01T00:00:00Z',
          dag: dagWithSchema,
          compiled: null,
        }),
      ),
      http.post('/api/v4/workflows/:id/runs', () =>
        HttpResponse.json({
          run: {
            id: 'run-42',
            workflow_version_id: 'v-2',
            status: 'pending',
            inputs: { query: 'test' },
          },
        }),
      ),
    );

    const user = userEvent.setup();

    // Render with a route that includes run detail so navigation can be verified
    let navigatedTo: string | null = null;
    render(
      <MemoryRouter initialEntries={['/workflows/wf-1']}>
        <Routes>
          <Route path="/workflows/:workflowId" element={<WorkflowBuilderPage />} />
          <Route
            path="/workflows/runs/:runId"
            element={<div data-testid="run-detail-placeholder">Run detail</div>}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    // Open run modal
    await user.click(screen.getByRole('button', { name: /^run$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('inputs-form-modal')).toBeInTheDocument();
    });

    // Fill in query and submit
    const queryInput = screen.getByLabelText('query');
    await user.type(queryInput, 'test');

    await user.click(screen.getByRole('button', { name: /run workflow/i }));

    // Should navigate to run detail page
    await waitFor(() => {
      expect(screen.getByTestId('run-detail-placeholder')).toBeInTheDocument();
    });
  });

  test('createRun 422 -> error shown in form', async () => {
    server.use(
      http.post('/api/v4/workflows/:id/runs', () =>
        HttpResponse.json(
          {
            detail: {
              type: 'inputs_invalid',
              message: 'Invalid inputs provided',
              errors: [{ message: 'field x is bad' }],
            },
          },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });

    // Open run modal
    await user.click(screen.getByRole('button', { name: /^run$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('inputs-form-modal')).toBeInTheDocument();
    });

    // Submit (schema is {} so it's valid immediately)
    await user.click(screen.getByRole('button', { name: /run workflow/i }));

    // Error should be shown in the form
    await waitFor(() => {
      expect(screen.getByText(/invalid inputs provided/i)).toBeInTheDocument();
    });
  });
});
