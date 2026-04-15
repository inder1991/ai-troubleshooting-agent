import { useMemo, useState } from 'react';
import type { PredicateExpr, RefExpr } from '../../../../types';
import { RefPicker, type RefSource } from '../RefPicker/RefPicker';
import {
  FROZEN_OPS,
  isUnaryOp,
  opsForFieldType,
  type FieldType,
  type SimpleOp,
} from './predicateTypes';

interface Props {
  value?: PredicateExpr;
  onChange: (p: PredicateExpr) => void;
  refSources: RefSource[];
}

function resolveFieldType(
  sources: RefSource[],
  ref: RefExpr,
): FieldType {
  const r = ref.ref;
  const src =
    r.from === 'node'
      ? sources.find(
          (s) => s.kind === 'node' && s.nodeId === (r as { node_id: string }).node_id,
        )
      : sources.find((s) => s.kind === r.from);
  if (!src) return 'unknown';
  // For node refs the stored path is `output.<rest>`; schema describes `output`
  // already (sources[].schema is the node's output schema). Strip prefix.
  let path = r.path;
  if (r.from === 'node' && path.startsWith('output.')) path = path.slice('output.'.length);
  else if (r.from === 'node' && path === 'output') return 'unknown';
  const parts = path.split('.').filter(Boolean);
  let cur: unknown = src.schema;
  for (const p of parts) {
    if (!cur || typeof cur !== 'object') return 'unknown';
    const c = cur as { properties?: Record<string, unknown>; items?: unknown };
    if (c.properties && p in c.properties) cur = c.properties[p];
    else return 'unknown';
  }
  if (cur && typeof cur === 'object') {
    const t = (cur as { type?: string }).type;
    if (t === 'string' || t === 'boolean' || t === 'integer' || t === 'number')
      return t;
  }
  return 'unknown';
}

function coerceLiteral(raw: string, t: FieldType): unknown {
  if (t === 'integer') {
    const n = parseInt(raw, 10);
    return Number.isNaN(n) ? raw : n;
  }
  if (t === 'number') {
    const n = parseFloat(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (t === 'boolean') return raw === 'true';
  return raw;
}

export function SimplePredicate({ value: _value, onChange, refSources }: Props) {
  const [fieldRef, setFieldRef] = useState<RefExpr | null>(null);
  const [op, setOp] = useState<SimpleOp | ''>('');
  const [rawValue, setRawValue] = useState<string>('');
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);

  const fieldType: FieldType = useMemo(
    () => (fieldRef ? resolveFieldType(refSources, fieldRef) : 'unknown'),
    [fieldRef, refSources],
  );
  const allowedOps = useMemo(
    () => (fieldRef ? opsForFieldType(fieldType) : FROZEN_OPS.slice()),
    [fieldRef, fieldType],
  );

  // If current op becomes disallowed after field change, reset.
  const effectiveOp = op && allowedOps.includes(op as SimpleOp) ? op : '';

  const needsValue = !!effectiveOp && !isUnaryOp(effectiveOp as SimpleOp);
  const complete =
    !!fieldRef &&
    !!effectiveOp &&
    (!needsValue || rawValue.length > 0);

  function buildAst(): PredicateExpr | null {
    if (!fieldRef || !effectiveOp) return null;
    const ref = fieldRef;
    const lit = { literal: coerceLiteral(rawValue, fieldType) };
    switch (effectiveOp as SimpleOp) {
      case 'eq':
        return { op: 'eq', args: [ref, lit] } as PredicateExpr;
      case 'neq':
        return {
          op: 'not',
          args: [{ op: 'eq', args: [ref, lit] }],
        } as unknown as PredicateExpr;
      case 'contains':
        return { op: 'in', args: [lit, ref] } as PredicateExpr;
      case 'not_contains':
        return {
          op: 'not',
          args: [{ op: 'in', args: [lit, ref] }],
        } as unknown as PredicateExpr;
      case 'exists':
        return { op: 'exists', args: [ref] } as PredicateExpr;
      case 'not_exists':
        return {
          op: 'not',
          args: [{ op: 'exists', args: [ref] }],
        } as unknown as PredicateExpr;
    }
  }

  function handleApply() {
    const ast = buildAst();
    if (ast) onChange(ast);
  }

  function fieldRefSummary(r: RefExpr): string {
    const v = r.ref;
    return v.from === 'node'
      ? `node.${(v as { node_id: string }).node_id}.${v.path}`
      : `${v.from}.${v.path}`;
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-wr-border bg-wr-surface p-3">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-wr-text-muted">Field</span>
        {fieldRef && (
          <div className="rounded-md border border-wr-border bg-wr-elevated px-2 py-1 font-mono text-xs text-wr-text">
            {fieldRefSummary(fieldRef)}
          </div>
        )}
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="self-start rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated"
        >
          {fieldRef ? 'Change field' : 'Pick field'}
        </button>
        {pickerOpen && (
          <RefPicker
            sources={refSources}
            value={fieldRef ?? undefined}
            onChange={(e) => {
              setFieldRef(e);
              setPickerOpen(false);
            }}
            onClose={() => setPickerOpen(false)}
          />
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor="predicate-op"
          className="text-xs font-medium text-wr-text-muted"
        >
          Operator
        </label>
        <select
          id="predicate-op"
          aria-label="Operator"
          value={effectiveOp}
          disabled={!fieldRef}
          onChange={(e) => setOp(e.target.value as SimpleOp)}
          className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text disabled:opacity-50"
        >
          <option value="">(choose)</option>
          {allowedOps.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>

      {needsValue && (
        <div className="flex flex-col gap-1">
          <label
            htmlFor="predicate-value"
            className="text-xs font-medium text-wr-text-muted"
          >
            Value
          </label>
          {fieldType === 'boolean' ? (
            <select
              id="predicate-value"
              aria-label="Value"
              value={rawValue}
              onChange={(e) => setRawValue(e.target.value)}
              className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
            >
              <option value="">(choose)</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              id="predicate-value"
              type={fieldType === 'integer' || fieldType === 'number' ? 'number' : 'text'}
              aria-label="Value"
              value={rawValue}
              onChange={(e) => setRawValue(e.target.value)}
              className="rounded-md border border-wr-border bg-wr-surface px-2 py-1.5 text-sm text-wr-text"
            />
          )}
        </div>
      )}

      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={handleApply}
          disabled={!complete}
          className="rounded-md border border-wr-border bg-wr-accent px-3 py-1.5 text-sm text-wr-on-accent hover:bg-wr-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Apply
        </button>
      </div>
    </div>
  );
}

export default SimplePredicate;
