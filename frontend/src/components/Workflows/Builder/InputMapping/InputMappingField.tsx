import { useMemo, useState } from 'react';
import type {
  MappingExpr,
  LiteralExpr,
  RefExpr,
  TransformExpr,
} from '../../../../types';
import { MappingModeToggle, type MappingMode } from './MappingModeToggle';
import { RefPicker, type RefSource } from '../RefPicker/RefPicker';

interface Props {
  fieldName: string;
  fieldSchema: { type?: string; enum?: unknown[] } & Record<string, unknown>;
  value?: MappingExpr;
  onChange: (v: MappingExpr) => void;
  refSources: RefSource[];
  /** recursion guard for transform args */
  depth?: number;
}

function isLiteral(v?: MappingExpr): v is LiteralExpr {
  return !!v && 'literal' in (v as LiteralExpr);
}
function isRef(v?: MappingExpr): v is RefExpr {
  return !!v && 'ref' in (v as RefExpr);
}
function isTransform(v?: MappingExpr): v is TransformExpr {
  return (
    !!v && 'op' in (v as TransformExpr) && 'args' in (v as TransformExpr)
  );
}

function detectMode(v?: MappingExpr): MappingMode {
  if (!v) return 'literal';
  if (isLiteral(v)) return 'literal';
  if (isRef(v)) return v.ref.from;
  if (isTransform(v)) return 'transform';
  return 'literal';
}

export function InputMappingField({
  fieldName,
  fieldSchema,
  value,
  onChange,
  refSources,
  depth = 0,
}: Props) {
  const [mode, setMode] = useState<MappingMode>(detectMode(value));
  const [advanced, setAdvanced] = useState<boolean>(mode === 'transform');
  const [pickerOpen, setPickerOpen] = useState<null | 'input' | 'node' | 'env'>(
    null,
  );

  // Local literal scratch so uncontrolled parents (and mode switches)
  // don't drop user keystrokes.
  const [literalScratch, setLiteralScratch] = useState<unknown>(
    isLiteral(value) ? value.literal : '',
  );
  const literalValue = isLiteral(value) ? (value.literal as unknown) : literalScratch;
  const [transformScratch, setTransformScratch] = useState<TransformExpr>(
    isTransform(value) ? value : { op: 'coalesce', args: [] },
  );
  const transformValue = isTransform(value) ? value : transformScratch;

  const schemaType = (fieldSchema?.type as string) ?? 'string';
  const enumOptions = Array.isArray(fieldSchema?.enum)
    ? (fieldSchema.enum as unknown[])
    : null;

  function setModeAndMaybeOpen(m: MappingMode) {
    setMode(m);
    if (m === 'input' || m === 'node' || m === 'env') {
      setPickerOpen(m);
    } else {
      setPickerOpen(null);
    }
  }

  function emitLiteral(v: unknown) {
    setLiteralScratch(v);
    onChange({ literal: v });
  }

  const renderLiteralWidget = () => {
    if (enumOptions) {
      return (
        <select
          aria-label={fieldName}
          value={literalValue as string}
          onChange={(e) => emitLiteral(e.target.value)}
          className="w-full rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
        >
          <option value="">(select)</option>
          {enumOptions.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      );
    }
    if (schemaType === 'boolean') {
      return (
        <label className="inline-flex items-center gap-2 text-sm text-wr-text">
          <input
            type="checkbox"
            aria-label={fieldName}
            checked={literalValue === true}
            onChange={(e) => emitLiteral(e.target.checked)}
            className="accent-wr-accent"
          />
          <span>{fieldName}</span>
        </label>
      );
    }
    if (schemaType === 'integer' || schemaType === 'number') {
      return (
        <input
          type="number"
          aria-label={fieldName}
          value={
            typeof literalValue === 'number'
              ? (literalValue as number)
              : (literalValue as string) ?? ''
          }
          step={schemaType === 'integer' ? 1 : 'any'}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') {
              emitLiteral('');
              return;
            }
            const n = schemaType === 'integer' ? parseInt(raw, 10) : parseFloat(raw);
            emitLiteral(Number.isNaN(n) ? raw : n);
          }}
          className="w-full rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
        />
      );
    }
    return (
      <input
        type="text"
        aria-label={fieldName}
        value={(literalValue as string) ?? ''}
        onChange={(e) => emitLiteral(e.target.value)}
        className="w-full rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
      />
    );
  };

  const renderRefSummary = () => {
    if (!isRef(value)) return null;
    const r = value.ref;
    const body =
      r.from === 'node'
        ? `node.${(r as { node_id: string }).node_id}.${r.path}`
        : `${r.from}.${r.path}`;
    return (
      <div className="rounded-md border border-wr-border bg-wr-elevated px-2 py-1 font-mono text-xs text-wr-text">
        {body}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-wr-text-muted">{fieldName}</span>
        <div className="flex items-center gap-2">
          <MappingModeToggle
            mode={mode}
            onChange={setModeAndMaybeOpen}
            showTransform={advanced}
          />
          {depth === 0 && (
            <button
              type="button"
              onClick={() => setAdvanced((a) => !a)}
              aria-pressed={advanced}
              className="text-xs text-wr-accent hover:underline"
            >
              {advanced ? 'Hide advanced' : 'Advanced'}
            </button>
          )}
        </div>
      </div>

      {mode === 'literal' && renderLiteralWidget()}

      {(mode === 'input' || mode === 'node' || mode === 'env') && (
        <div className="flex flex-col gap-2">
          {renderRefSummary()}
          <button
            type="button"
            onClick={() => setPickerOpen(mode)}
            className="self-start rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated"
          >
            {isRef(value) ? 'Change reference' : 'Pick reference'}
          </button>
          {pickerOpen === mode && (
            <RefPicker
              sources={refSources}
              restrictKind={mode}
              value={isRef(value) ? value : undefined}
              onChange={(e) => {
                onChange(e);
                setPickerOpen(null);
              }}
              onClose={() => setPickerOpen(null)}
            />
          )}
        </div>
      )}

      {mode === 'transform' && (
        <TransformEditor
          value={transformValue}
          onChange={(v) => {
            if (isTransform(v)) setTransformScratch(v);
            onChange(v);
          }}
          refSources={refSources}
          depth={depth}
        />
      )}
    </div>
  );
}

interface TransformEditorProps {
  value: TransformExpr;
  onChange: (v: MappingExpr) => void;
  refSources: RefSource[];
  depth: number;
}

function TransformEditor({
  value,
  onChange,
  refSources,
  depth,
}: TransformEditorProps) {
  const args = value.args ?? [];

  function updateOp(op: 'coalesce' | 'concat') {
    onChange({ op, args });
  }
  function setArg(i: number, v: MappingExpr) {
    const next = args.slice();
    next[i] = v;
    onChange({ op: value.op, args: next });
  }
  function addArg() {
    onChange({ op: value.op, args: [...args, { literal: '' }] });
  }
  function removeArg(i: number) {
    onChange({
      op: value.op,
      args: args.slice(0, i).concat(args.slice(i + 1)),
    });
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-wr-border bg-wr-surface p-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-wr-text-muted" htmlFor="transform-op">
          Op
        </label>
        <select
          id="transform-op"
          aria-label="Transform op"
          value={value.op}
          onChange={(e) => updateOp(e.target.value as 'coalesce' | 'concat')}
          className="rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text"
        >
          <option value="coalesce">coalesce</option>
          <option value="concat">concat</option>
        </select>
      </div>
      <div className="flex flex-col gap-2">
        {args.map((a, i) => (
          <div
            key={i}
            className="flex items-start gap-2 rounded-md border border-wr-border bg-wr-bg p-2"
          >
            <div className="flex-1">
              {depth === 0 ? (
                <InputMappingField
                  fieldName={`arg ${i}`}
                  fieldSchema={{ type: 'string' }}
                  value={a}
                  onChange={(v) => setArg(i, v)}
                  refSources={refSources}
                  depth={depth + 1}
                />
              ) : (
                <textarea
                  aria-label={`arg ${i} json`}
                  value={JSON.stringify(a)}
                  onChange={(e) => {
                    try {
                      setArg(i, JSON.parse(e.target.value));
                    } catch {
                      /* ignore until valid */
                    }
                  }}
                  className="w-full rounded-md border border-wr-border bg-wr-surface px-2 py-1 font-mono text-xs text-wr-text"
                  rows={2}
                />
              )}
            </div>
            <button
              type="button"
              onClick={() => removeArg(i)}
              className="text-xs text-wr-text-muted hover:text-wr-status-error"
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addArg}
          className="self-start rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated"
        >
          Add arg
        </button>
      </div>
    </div>
  );
}

export default InputMappingField;
