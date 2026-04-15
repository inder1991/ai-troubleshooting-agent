import { describe, expect, test, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowHeader } from '../WorkflowHeader';
import type { WorkflowDetail, VersionSummary } from '../../../../types';

const wf: WorkflowDetail = {
  id: 'wf-1',
  name: 'Disk pressure triage',
  description: 'Investigate disk pressure on a node',
  created_at: '2026-04-10T12:00:00Z',
  created_by: 'me',
};

const versions: VersionSummary[] = [
  { version_id: 'v1id', workflow_id: 'wf-1', version: 1, created_at: '2026-04-10T12:00:00Z' },
  { version_id: 'v2id', workflow_id: 'wf-1', version: 2, created_at: '2026-04-11T12:00:00Z' },
];

function renderIt(overrides: Partial<React.ComponentProps<typeof WorkflowHeader>> = {}) {
  const props = {
    workflow: wf,
    versions,
    activeVersion: 2,
    selectedVersion: 2,
    canSave: true,
    onSelectVersion: vi.fn(),
    onForkVersion: vi.fn(),
    onSave: vi.fn(),
    onRun: vi.fn(),
    ...overrides,
  };
  render(<WorkflowHeader {...props} />);
  return props;
}

describe('WorkflowHeader', () => {
  test('renders workflow name and description', () => {
    renderIt();
    expect(screen.getByRole('heading', { name: /disk pressure triage/i })).toBeInTheDocument();
    expect(screen.getByText(/investigate disk pressure on a node/i)).toBeInTheDocument();
  });

  test('Save as new version button click calls onSave exactly once', () => {
    const props = renderIt();
    expect(props.onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /save as new version/i }));
    expect(props.onSave).toHaveBeenCalledTimes(1);
  });

  test('Save disabled when canSave is false', () => {
    renderIt({ canSave: false });
    expect(screen.getByRole('button', { name: /save as new version/i })).toBeDisabled();
  });

  test('Save disabled and spinner visible when saving is true', () => {
    renderIt({ saving: true });
    const btn = screen.getByRole('button', { name: /save/i });
    expect(btn).toBeDisabled();
    // spinner via data-testid
    expect(screen.getByTestId('save-spinner')).toBeInTheDocument();
  });

  test('Run button calls onRun', () => {
    const props = renderIt();
    fireEvent.click(screen.getByRole('button', { name: /^run$/i }));
    expect(props.onRun).toHaveBeenCalledTimes(1);
  });

  test('Version switcher selection bubbles to onSelectVersion', () => {
    const props = renderIt();
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: '1' } });
    expect(props.onSelectVersion).toHaveBeenCalledWith(1);
  });

  test('Version switcher Edit bubbles to onForkVersion', () => {
    const props = renderIt();
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    expect(props.onForkVersion).toHaveBeenCalledWith(2);
  });
});
