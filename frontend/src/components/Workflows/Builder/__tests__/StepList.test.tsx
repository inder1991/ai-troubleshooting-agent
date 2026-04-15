import { describe, expect, test, vi } from 'vitest';
import {
  act,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepList, extractStepDependencies } from '../StepList';
import type { StepSpec, PredicateExpr, MappingExpr } from '../../../../types';

function makeStep(over: Partial<StepSpec> = {}): StepSpec {
  return {
    id: 'step1',
    agent: 'log_analyzer',
    agent_version: 1,
    inputs: {},
    ...over,
  };
}

/** Minimal DataTransfer stub. */
function makeDataTransfer(): DataTransfer {
  const store: Record<string, string> = {};
  return {
    data: store,
    dropEffect: 'move',
    effectAllowed: 'move',
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    types: [] as unknown as readonly string[],
    clearData: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
    getData: (k: string) => store[k] ?? '',
    setData: (k: string, v: string) => {
      store[k] = v;
    },
    setDragImage: () => {},
  } as unknown as DataTransfer;
}

/** Fire a drag-and-drop from source index -> target index. */
function dragAndDrop(
  rows: HTMLElement[],
  fromIdx: number,
  toIdx: number,
  placement: 'before' | 'after' = 'before',
) {
  const dt = makeDataTransfer();
  const fromHandle = within(rows[fromIdx]).getByTestId('drag-handle');
  fireEvent.dragStart(fromHandle, { dataTransfer: dt });

  // Position a dragOver event inside target row. clientY near top = before,
  // near bottom = after.
  const target = rows[toIdx];
  // jsdom doesn't compute layout. Emulate via boundingClientRect.
  const rect = { top: 0, bottom: 40, height: 40, left: 0, right: 100, width: 100, x: 0, y: 0, toJSON: () => ({}) };
  target.getBoundingClientRect = () => rect as DOMRect;
  const clientY = placement === 'before' ? 5 : 35;
  // jsdom doesn't forward clientY to DragEvent; pass via a side channel.
  dt.setData('text/y', String(clientY));
  fireEvent.dragOver(target, { dataTransfer: dt, clientY });
  fireEvent.drop(target, { dataTransfer: dt, clientY });
  fireEvent.dragEnd(fromHandle, { dataTransfer: dt });
}

describe('extractStepDependencies', () => {
  test('returns node_ids from inputs MappingExpr refs', () => {
    const step = makeStep({
      inputs: {
        a: { ref: { from: 'node', node_id: 'n1', path: 'x' } } as MappingExpr,
        b: { literal: 'hello' } as MappingExpr,
        c: { ref: { from: 'input', path: 'foo' } } as MappingExpr,
      },
    });
    const deps = extractStepDependencies(step);
    expect(deps).toEqual(['n1']);
  });

  test('returns node_ids from when-predicate and inputs combined', () => {
    const when: PredicateExpr = {
      op: 'and',
      args: [
        {
          op: 'eq',
          left: { ref: { from: 'node', node_id: 'n2', path: 'status' } },
          right: { literal: 'ok' },
        },
        {
          op: 'not',
          arg: {
            op: 'exists',
            args: [{ ref: { from: 'node', node_id: 'n3', path: 'x' } }],
          },
        },
      ],
    };
    const step = makeStep({
      inputs: {
        a: {
          op: 'coalesce',
          args: [
            { ref: { from: 'node', node_id: 'n1', path: 'x' } },
            { literal: '' },
          ],
        } as MappingExpr,
      },
      when,
    });
    const deps = extractStepDependencies(step);
    expect(new Set(deps)).toEqual(new Set(['n1', 'n2', 'n3']));
  });
});

describe('StepList', () => {
  const steps: StepSpec[] = [
    makeStep({ id: 's1' }),
    makeStep({
      id: 's2',
      inputs: {
        x: { ref: { from: 'node', node_id: 's1', path: 'a' } } as MappingExpr,
      },
    }),
    makeStep({ id: 's3' }),
  ];

  test('renders one row per step', () => {
    render(
      <StepList
        steps={steps}
        onSelect={vi.fn()}
        onReorder={vi.fn()}
      />,
    );
    expect(screen.getByText('s1')).toBeInTheDocument();
    expect(screen.getByText('s2')).toBeInTheDocument();
    expect(screen.getByText('s3')).toBeInTheDocument();
  });

  test('clicking a row calls onSelect with step id', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <StepList
        steps={steps}
        onSelect={onSelect}
        onReorder={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: /s2/i }));
    expect(onSelect).toHaveBeenCalledWith('s2');
  });

  test('passes errors through to row badge', () => {
    render(
      <StepList
        steps={steps}
        onSelect={vi.fn()}
        onReorder={vi.fn()}
        errorsByStepId={{
          s2: [
            { path: 'steps[1].id', message: 'bad' },
            { path: 'steps[1].agent', message: 'bad' },
          ],
        }}
      />,
    );
    expect(screen.getByLabelText(/2 errors?/i)).toBeInTheDocument();
  });

  test('rejects dragging a dependency below its consumer and shows pill', () => {
    vi.useFakeTimers();
    const onReorder = vi.fn();
    render(
      <StepList
        steps={steps}
        onSelect={vi.fn()}
        onReorder={onReorder}
      />,
    );
    const rows = screen.getAllByTestId('step-row');
    // Move s1 (idx 0) below s2 (idx 1). s2 refs s1, so this must be rejected.
    dragAndDrop(rows, 0, 1, 'after');
    expect(onReorder).not.toHaveBeenCalled();
    expect(
      screen.getByText(/cannot place .* before its dependency/i),
    ).toBeInTheDocument();
    // Pill auto-dismisses after 3s.
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(
      screen.queryByText(/cannot place .* before its dependency/i),
    ).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  test('accepts a valid reorder and calls onReorder with new ordering', () => {
    const onReorder = vi.fn();
    render(
      <StepList
        steps={steps}
        onSelect={vi.fn()}
        onReorder={onReorder}
      />,
    );
    const rows = screen.getAllByTestId('step-row');
    // Move s3 (idx 2) up to before s2 (idx 1). s3 has no deps, valid.
    dragAndDrop(rows, 2, 1, 'before');
    expect(onReorder).toHaveBeenCalledTimes(1);
    const newOrder = onReorder.mock.calls[0][0] as StepSpec[];
    expect(newOrder.map((s) => s.id)).toEqual(['s1', 's3', 's2']);
  });
});
