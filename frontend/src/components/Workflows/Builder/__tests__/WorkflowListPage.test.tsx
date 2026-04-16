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
});
