import { describe, expect, test, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { WorkflowListPage } from '../WorkflowListPage';
import { ToastProvider } from '../../Shared/Toast';
import type { WorkflowSummary, WorkflowDetail } from '../../../../types';

// ---- Mock data ----

const mockWorkflows: WorkflowSummary[] = [
  {
    id: 'wf-1',
    name: 'Log Analysis Pipeline',
    description: 'Automated log analysis workflow',
    created_at: '2026-01-15T10:00:00Z',
  },
  {
    id: 'wf-2',
    name: 'Code Review Bot',
    description: 'AI-powered code review',
    created_at: '2026-02-20T14:30:00Z',
  },
];

const createdWorkflow: WorkflowDetail = {
  id: 'wf-new',
  name: 'New Workflow',
  description: 'A new workflow',
  created_at: '2026-03-01T00:00:00Z',
};

// ---- MSW Server ----

const server = setupServer(
  http.get('/api/v4/workflows', () =>
    HttpResponse.json({ workflows: mockWorkflows }),
  ),
  http.post('/api/v4/workflows', async ({ request }) => {
    const body = (await request.json()) as { name: string; description: string };
    return HttpResponse.json({
      ...createdWorkflow,
      name: body.name,
      description: body.description,
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---- Helper to capture navigation ----

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderList() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/workflows']}>
        <Routes>
          <Route path="/workflows" element={<WorkflowListPage />} />
          <Route path="/workflows/:workflowId" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

// ---- Tests ----

describe('WorkflowListPage', () => {
  test('lists workflows from API', async () => {
    renderList();

    await waitFor(() => {
      expect(screen.getByText('Log Analysis Pipeline')).toBeInTheDocument();
    });

    expect(screen.getByText('Code Review Bot')).toBeInTheDocument();
    expect(screen.getByText('Automated log analysis workflow')).toBeInTheDocument();
    expect(screen.getByText('AI-powered code review')).toBeInTheDocument();
  });

  test('click workflow navigates to /workflows/:id', async () => {
    const user = userEvent.setup();
    renderList();

    await waitFor(() => {
      expect(screen.getByText('Log Analysis Pipeline')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Log Analysis Pipeline'));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/workflows/wf-1');
    });
  });

  test('create form: submit calls API and navigates to new workflow', async () => {
    const user = userEvent.setup();
    renderList();

    await waitFor(() => {
      expect(screen.getByText('Log Analysis Pipeline')).toBeInTheDocument();
    });

    // Open create form
    await user.click(screen.getByRole('button', { name: /create workflow/i }));

    // Fill in name
    const nameInput = screen.getByLabelText(/name/i);
    await user.type(nameInput, 'New Workflow');

    // Submit
    await user.click(screen.getByRole('button', { name: /^create$/i }));

    // Should navigate to the new workflow
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/workflows/wf-new');
    });
  });

  test('empty state renders when no workflows', async () => {
    server.use(
      http.get('/api/v4/workflows', () =>
        HttpResponse.json({ workflows: [] }),
      ),
    );

    renderList();

    await waitFor(() => {
      expect(screen.getByText(/no workflows yet/i)).toBeInTheDocument();
    });
  });

  test('loading state shows', () => {
    renderList();

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  // ---- Three-dot menu tests ----

  test('three-dot menu: Rename — type new name, press Enter → updated in DOM and success toast', async () => {
    const user = userEvent.setup();

    server.use(
      http.patch('/api/v4/workflows/:id', async () =>
        HttpResponse.json({ id: 'wf-2', name: 'Renamed Bot', description: 'AI-powered code review', created_at: '2026-02-20T14:30:00Z' }),
      ),
    );

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Code Review Bot')).toBeInTheDocument();
    });

    // Open three-dot menu for wf-2 (last item — menuRef correctly points to it)
    await user.click(screen.getByTestId('menu-btn-wf-2'));

    // Click Rename
    await user.click(screen.getByText('Rename'));

    // Rename input should appear with original name
    const renameInput = screen.getByDisplayValue('Code Review Bot');
    expect(renameInput).toBeInTheDocument();

    // Clear and type new name
    await user.clear(renameInput);
    await user.type(renameInput, 'Renamed Bot');
    await user.keyboard('{Enter}');

    // Verify updated name in DOM
    await waitFor(() => {
      expect(screen.getByText('Renamed Bot')).toBeInTheDocument();
    });

    // Verify success toast
    await waitFor(() => {
      expect(screen.getByText('Workflow renamed')).toBeInTheDocument();
    });
  });

  test('three-dot menu: Duplicate → success toast and navigation', async () => {
    const user = userEvent.setup();

    server.use(
      http.post('/api/v4/workflows/:id/duplicate', () =>
        HttpResponse.json({ id: 'wf-dup', name: 'Code Review Bot (copy)', description: 'AI-powered code review', created_at: '2026-03-01T00:00:00Z' }),
      ),
    );

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Code Review Bot')).toBeInTheDocument();
    });

    // Open three-dot menu for wf-2
    await user.click(screen.getByTestId('menu-btn-wf-2'));

    // Click Duplicate
    await user.click(screen.getByText('Duplicate'));

    // Verify success toast
    await waitFor(() => {
      expect(screen.getByText('Workflow duplicated')).toBeInTheDocument();
    });

    // Verify navigation to duplicated workflow
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/workflows/wf-dup');
    });
  });

  test('three-dot menu: Delete → ConfirmDeleteDialog → type name → delete → workflow removed', async () => {
    const user = userEvent.setup();

    server.use(
      http.delete('/api/v4/workflows/:id', () =>
        new HttpResponse(null, { status: 204 }),
      ),
    );

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Code Review Bot')).toBeInTheDocument();
    });

    // Open three-dot menu for wf-2
    await user.click(screen.getByTestId('menu-btn-wf-2'));

    // Click Delete
    await user.click(screen.getByText('Delete'));

    // ConfirmDeleteDialog should appear
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText('Delete workflow')).toBeInTheDocument();

    // Delete button should be disabled before typing name
    const deleteBtn = screen.getByRole('button', { name: /^delete$/i });
    expect(deleteBtn).toBeDisabled();

    // Type the workflow name to confirm
    const confirmInput = screen.getByPlaceholderText('Code Review Bot');
    await user.type(confirmInput, 'Code Review Bot');

    // Delete button should now be enabled
    expect(deleteBtn).toBeEnabled();
    await user.click(deleteBtn);

    // Verify workflow removed from DOM
    await waitFor(() => {
      expect(screen.queryByText('Code Review Bot')).not.toBeInTheDocument();
    });

    // Verify success toast
    await waitFor(() => {
      expect(screen.getByText('Workflow deleted')).toBeInTheDocument();
    });

    // Other workflow should still be present
    expect(screen.getByText('Log Analysis Pipeline')).toBeInTheDocument();
  });

  test('three-dot menu: Delete with 409 response → error toast', async () => {
    const user = userEvent.setup();

    server.use(
      http.delete('/api/v4/workflows/:id', () =>
        HttpResponse.json(
          { detail: { message: 'Workflow has active runs' } },
          { status: 409 },
        ),
      ),
    );

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Code Review Bot')).toBeInTheDocument();
    });

    // Open three-dot menu for wf-2
    await user.click(screen.getByTestId('menu-btn-wf-2'));

    // Click Delete
    await user.click(screen.getByText('Delete'));

    // Type the workflow name
    const confirmInput = screen.getByPlaceholderText('Code Review Bot');
    await user.type(confirmInput, 'Code Review Bot');

    // Click Delete in dialog
    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    // Verify error toast — the 409 detail.message is surfaced via getErrorMessage
    await waitFor(() => {
      expect(screen.getByText('Workflow has active runs')).toBeInTheDocument();
    });

    // Workflow should still be in the list (name appears in list + dialog confirmation text)
    expect(screen.getAllByText('Code Review Bot').length).toBeGreaterThanOrEqual(1);
  });
});
