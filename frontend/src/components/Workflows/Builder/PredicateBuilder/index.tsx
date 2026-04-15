import { useState } from 'react';
import type { PredicateExpr, RefExpr } from '../../../../types';
import { SimplePredicate } from './SimplePredicate';
import { AdvancedAstBuilder } from './AdvancedAstBuilder';
import type { RefSource } from '../RefPicker/RefPicker';

type Mode = 'simple' | 'advanced';

function isLeafClause(e: PredicateExpr | undefined): boolean {
  if (!e) return true;
  const op = (e as { op?: string }).op;
  if (op === 'eq' || op === 'in' || op === 'exists') return true;
  if (op === 'not') {
    const inner = (e as unknown as { args: [PredicateExpr] }).args?.[0];
    if (!inner) return false;
    const iop = (inner as { op?: string }).op;
    return iop === 'eq' || iop === 'in' || iop === 'exists';
  }
  return false;
}

function unwrapSingletonGroup(e: PredicateExpr): PredicateExpr | null {
  const op = (e as { op?: string }).op;
  if ((op === 'and' || op === 'or')) {
    const args = (e as { args: PredicateExpr[] }).args;
    if (args.length === 1 && isLeafClause(args[0])) return args[0];
  }
  if (isLeafClause(e)) return e;
  return null;
}

interface Props {
  value?: PredicateExpr;
  onChange: (v: PredicateExpr | undefined) => void;
  refSources: RefSource[];
  schemaByRef?: (ref: RefExpr) => unknown;
}

export function PredicateBuilder({
  value,
  onChange,
  refSources,
  schemaByRef,
}: Props) {
  const defaultMode: Mode = isLeafClause(value) ? 'simple' : 'advanced';
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [banner, setBanner] = useState<boolean>(false);

  function gotoAdvanced() {
    setBanner(false);
    if (value && !isLeafClause(value)) {
      // Already compound — just switch mode.
      setMode('advanced');
      return;
    }
    // Wrap leaf (or undefined) into and-group.
    if (value) {
      onChange({ op: 'and', args: [value] });
    }
    setMode('advanced');
  }

  function gotoSimple() {
    if (!value) {
      setMode('simple');
      return;
    }
    const reduced = unwrapSingletonGroup(value);
    if (reduced) {
      if (reduced !== value) onChange(reduced);
      setMode('simple');
      return;
    }
    // Cannot reduce — show banner
    setBanner(true);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1" role="group" aria-label="Predicate mode">
        <button
          type="button"
          aria-pressed={mode === 'simple'}
          onClick={() => gotoSimple()}
          className={
            'rounded-md border border-wr-border px-2 py-1 text-xs ' +
            (mode === 'simple'
              ? 'bg-wr-accent text-wr-on-accent'
              : 'bg-wr-surface text-wr-text hover:bg-wr-elevated')
          }
        >
          Simple
        </button>
        <button
          type="button"
          aria-pressed={mode === 'advanced'}
          onClick={() => gotoAdvanced()}
          className={
            'rounded-md border border-wr-border px-2 py-1 text-xs ' +
            (mode === 'advanced'
              ? 'bg-wr-accent text-wr-on-accent'
              : 'bg-wr-surface text-wr-text hover:bg-wr-elevated')
          }
        >
          Advanced
        </button>
      </div>

      {banner && (
        <div
          role="alert"
          className="rounded-md border border-wr-border bg-wr-elevated p-2 text-xs text-wr-text"
        >
          <div className="mb-2">
            This predicate cannot be represented as a simple predicate. Reset
            will discard the current expression.
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setBanner(false)}
              className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
            >
              Stay in advanced
            </button>
            <button
              type="button"
              onClick={() => {
                setBanner(false);
                onChange(undefined);
                setMode('simple');
              }}
              className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
            >
              Reset to simple
            </button>
          </div>
        </div>
      )}

      {mode === 'simple' ? (
        <SimplePredicate
          value={value}
          onChange={onChange}
          refSources={refSources}
        />
      ) : (
        <AdvancedAstBuilder
          value={value ?? ({ op: 'and', args: [] } as unknown as PredicateExpr)}
          onChange={onChange}
          refSources={refSources}
          schemaByRef={schemaByRef}
        />
      )}
    </div>
  );
}

export default PredicateBuilder;
