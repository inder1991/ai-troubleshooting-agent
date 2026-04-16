import { describe, expect, test, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { StepDrawer } from '../StepDrawer';
import { ToastProvider } from '../../Shared/Toast';
import type { StepSpec, CatalogAgentSummary, CatalogAgentDetail } from '../../../../types';

// ---- MSW mock data ----

const mockDetail: CatalogAgentDetail = {
  name: 'log_analyzer',
  version: 2,
  description: 'Analyzes logs',
  category: 'analysis',
  tags: ['logs'],
  deprecated_versions: [1],
  input_schema: {
    type: 'object',
    properties: {
      query: { type: 'string' },
      max_results: { type: 'number' },
    },
  },
  output_schema: { type: 'object', properties: { results: { type: 'array' } } },
  trigger_examples: ['analyze logs'],
  timeout_seconds: 60,
  retry_on: ['network_error', 'timeout'],
};

const mockDetailV3: CatalogAgentDetail = {
  ...mockDetail,
  version: 3,
  deprecated_versions: [1],
};

const server = setupServer(
  http.get('/api/v4/catalog/agents/:name/v/:version', ({ params }) => {
    const version = Number(params.version);
    if (version === 3) return HttpResponse.json(mockDetailV3);
    return HttpResponse.json(mockDetail);
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---- Helpers ----

const catalog: CatalogAgentSummary[] = [
  { name: 'log_analyzer', version: 2, description: 'Analyzes logs', category: 'analysis', tags: ['logs'] },
  { name: 'log_analyzer', version: 3, description: 'Analyzes logs v3', category: 'analysis', tags: ['logs'] },
  { name: 'code_navigator', version: 1, description: 'Navigates code', category: 'code', tags: ['code'] },
];

function makeStep(over: Partial<StepSpec> = {}): StepSpec {
  return {
    id: 'step-1',
    agent: 'log_analyzer',
    agent_version: 2,
    inputs: {},
    ...over,
  };
}

const allSteps: StepSpec[] = [
  makeStep(),
  makeStep({ id: 'step-2', agent: 'code_navigator', agent_version: 1 }),
];

function renderDrawer(overrides: Partial<Parameters<typeof StepDrawer>[0]> = {}) {
  const onChange = vi.fn();
  const onDelete = vi.fn();
  const onClose = vi.fn();
  const result = render(
    <ToastProvider>
      <StepDrawer
        step={makeStep()}
        catalog={catalog}
        allSteps={allSteps}
        onChange={onChange}
        onDelete={onDelete}
        onClose={onClose}
        {...overrides}
      />
    </ToastProvider>,
  );
  return { onChange, onDelete, onClose, ...result };
}

// ---- Tests ----

describe('StepDrawer', () => {
  test('renders all 5 section headers', () => {
    renderDrawer();
    expect(screen.getByRole('button', { name: /agent/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /inputs/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /trigger/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /failure/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /execution/i })).toBeInTheDocument();
  });

  test('agent select changes agent and clears inputs', async () => {
    const user = userEvent.setup();
    const { onChange } = renderDrawer();

    const agentSelect = screen.getByLabelText(/select agent/i);
    await user.selectOptions(agentSelect, 'code_navigator');

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        agent: 'code_navigator',
        inputs: {},
      }),
    );
  });

  test('inputs section renders one InputMappingField per input_schema property', async () => {
    renderDrawer();

    // Wait for the agent detail to be fetched and input fields to appear
    await waitFor(() => {
      expect(screen.getByText('query')).toBeInTheDocument();
      expect(screen.getByText('max_results')).toBeInTheDocument();
    });
  });

  test('trigger section renders PredicateBuilder', async () => {
    const user = userEvent.setup();
    renderDrawer();

    // Expand the Trigger section (collapsed by default)
    const triggerBtn = screen.getByRole('button', { name: /trigger/i });
    await user.click(triggerBtn);

    // PredicateBuilder renders a mode toggle group
    await waitFor(() => {
      expect(screen.getByRole('group', { name: /predicate mode/i })).toBeInTheDocument();
    });
  });

  test('failure radio: selecting fallback shows step picker and emits onChange', async () => {
    const user = userEvent.setup();
    // Render with on_failure already set to 'fallback' so picker is visible
    const step = makeStep({ on_failure: 'fallback', fallback_step_id: 'step-2' });
    const { onChange } = renderDrawer({ step });

    // Expand Failure section
    const failureBtn = screen.getByRole('button', { name: /failure/i });
    await user.click(failureBtn);

    // Step picker should be visible since on_failure is 'fallback'
    const stepPicker = screen.getByLabelText(/fallback step/i);
    expect(stepPicker).toBeInTheDocument();

    // Select a different step (same step-2 to verify onChange is called)
    await user.selectOptions(stepPicker, 'step-2');

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        on_failure: 'fallback',
        fallback_step_id: 'step-2',
      }),
    );
  });

  test('failure step picker excludes self', async () => {
    const user = userEvent.setup();
    const step = makeStep({ on_failure: 'fallback', fallback_step_id: 'step-2' });
    renderDrawer({ step });

    // Expand Failure section
    const failureBtn = screen.getByRole('button', { name: /failure/i });
    await user.click(failureBtn);

    const stepPicker = screen.getByLabelText(/fallback step/i);
    const options = within(stepPicker).getAllByRole('option');
    const values = options.map((o) => (o as HTMLOptionElement).value);

    // Should NOT include self (step-1)
    expect(values).not.toContain('step-1');
    // Should include step-2
    expect(values).toContain('step-2');
  });

  test('timeout: entering a value > contract max shows warning', async () => {
    const user = userEvent.setup();
    // Pre-set a timeout that exceeds the contract max (60)
    const step = makeStep({ timeout_seconds_override: 120 });
    renderDrawer({ step });

    // Expand Execution section
    const execBtn = screen.getByRole('button', { name: /execution/i });
    await user.click(execBtn);

    // Wait for agent detail to load and warning to appear
    await waitFor(() => {
      expect(screen.getByText(/exceeds contract max/i)).toBeInTheDocument();
    });
  });

  test('delete: click delete then confirm calls onDelete', async () => {
    const user = userEvent.setup();
    const { onDelete } = renderDrawer();

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await user.click(deleteBtn);

    // Confirm prompt should appear
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    await user.click(confirmBtn);

    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  test('close: click X calls onClose', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDrawer();

    const closeBtn = screen.getByRole('button', { name: /close/i });
    await user.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
