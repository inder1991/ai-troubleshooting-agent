import { useState } from 'react';

interface Props {
  workflowName: string;
  onConfirm: () => void;
  onCancel: () => void;
  deleting?: boolean;
}

export function ConfirmDeleteDialog({ workflowName, onConfirm, onCancel, deleting }: Props) {
  const [input, setInput] = useState('');
  const matches = input === workflowName;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-wr-border bg-wr-surface p-6 space-y-4">
        <h2 className="text-lg font-semibold text-wr-text">Delete workflow</h2>
        <p className="text-sm text-wr-text-muted">
          This will permanently remove this workflow from the list. Existing runs and
          their data will remain accessible.
        </p>
        <p className="text-sm text-wr-text">
          Type <span className="font-mono font-semibold text-red-400">{workflowName}</span> to confirm.
        </p>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={workflowName}
          className="w-full rounded-md border border-wr-border bg-wr-bg px-3 py-2 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-red-500"
          autoFocus
        />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel}
            className="rounded-md border border-wr-border bg-wr-surface px-4 py-1.5 text-sm text-wr-text hover:bg-wr-elevated">
            Cancel
          </button>
          <button type="button" onClick={onConfirm} disabled={!matches || deleting}
            className="rounded-md bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50">
            {deleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
