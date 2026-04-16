import { useEffect, useMemo, useState } from 'react';
import type { RefExpr } from '../../../../types';
import { listPaths } from './schemaPaths';
import { PathAutocomplete } from './PathAutocomplete';

export type RefSource = {
  kind: 'input' | 'node' | 'env';
  label: string;
  nodeId?: string;
  schema: object;
};

interface Props {
  sources: RefSource[];
  value?: RefExpr;
  onChange: (e: RefExpr) => void;
  onClose: () => void;
  /** Restrict picker to a single source kind (used from InputMappingField). */
  restrictKind?: 'input' | 'node' | 'env';
}

function sourceKey(s: RefSource): string {
  return s.kind === 'node' ? `node:${s.nodeId ?? ''}` : s.kind;
}

export function RefPicker({
  sources,
  value,
  onChange,
  onClose,
  restrictKind,
}: Props) {
  const visible = useMemo(
    () => (restrictKind ? sources.filter((s) => s.kind === restrictKind) : sources),
    [sources, restrictKind],
  );

  const [selectedKey, setSelectedKey] = useState<string | null>(() => {
    if (value && 'ref' in value) {
      const r = value.ref;
      if (r.from === 'node')
        return `node:${(r as { node_id: string }).node_id}`;
      return r.from;
    }
    return visible.length === 1 ? sourceKey(visible[0]) : null;
  });
  const [step, setStep] = useState<'source' | 'path'>(
    value ? 'path' : visible.length === 1 ? 'path' : 'source',
  );
  const initialPath =
    value && 'ref' in value
      ? value.ref.from === 'node'
        ? (value.ref.path ?? '').replace(/^output\.?/, '')
        : value.ref.path
      : '';
  const [path, setPath] = useState<string>(initialPath);

  const source = useMemo(
    () => visible.find((s) => sourceKey(s) === selectedKey) ?? null,
    [visible, selectedKey],
  );

  const suggestions = useMemo(() => {
    if (!source) return [];
    return listPaths(source.schema);
  }, [source]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  function handleConfirm() {
    if (!source || !path.trim()) return;
    if (source.kind === 'node') {
      if (!source.nodeId) return;
      onChange({
        ref: {
          from: 'node',
          node_id: source.nodeId,
          path: `output.${path.trim()}`,
        },
      });
    } else if (source.kind === 'input') {
      onChange({ ref: { from: 'input', path: path.trim() } });
    } else {
      onChange({ ref: { from: 'env', path: path.trim() } });
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Reference picker"
      className="w-full rounded-md border border-wr-border bg-wr-surface p-4 shadow-lg"
    >
      {step === 'source' ? (
        <div>
          <div className="mb-3 text-sm font-medium text-wr-text">
            Pick a source
          </div>
          <div
            role="radiogroup"
            aria-label="Reference sources"
            className="flex flex-col gap-1"
          >
            {visible.map((s) => {
              const key = sourceKey(s);
              const checked = key === selectedKey;
              return (
                <label
                  key={key}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${
                    checked
                      ? 'border-wr-accent bg-wr-elevated text-wr-text'
                      : 'border-wr-border bg-wr-surface text-wr-text-muted hover:bg-wr-elevated'
                  }`}
                >
                  <input
                    type="radio"
                    name="ref-source"
                    aria-label={s.label}
                    checked={checked}
                    onChange={() => setSelectedKey(key)}
                    className="accent-wr-accent"
                  />
                  <span>{s.label}</span>
                  <span className="ml-auto font-mono text-xs text-wr-text-muted">
                    {s.kind}
                  </span>
                </label>
              );
            })}
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => setStep('path')}
              disabled={!selectedKey}
              className="rounded-md border border-wr-border bg-wr-accent px-3 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium text-wr-text">
              Path in <span className="font-mono">{source?.label}</span>
            </div>
            {visible.length > 1 && (
              <button
                type="button"
                onClick={() => setStep('source')}
                className="text-xs text-wr-accent hover:underline"
              >
                Back
              </button>
            )}
          </div>
          <PathAutocomplete
            value={path}
            onChange={setPath}
            suggestions={suggestions}
            displayPrefix={source?.kind === 'node' ? 'output.' : undefined}
            placeholder={source?.kind === 'node' ? 'summary' : 'field.path'}
            onEscape={onClose}
          />
          <div className="mt-4 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-wr-border bg-wr-surface px-3 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!path.trim()}
              className="rounded-md border border-wr-border bg-wr-accent px-3 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              Select
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default RefPicker;
