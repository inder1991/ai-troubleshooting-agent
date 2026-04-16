import type { PredicateExpr, RefExpr } from '../../../../types';
import { SimplePredicate } from './SimplePredicate';
import type { RefSource } from '../RefPicker/RefPicker';

type Compound = { op: 'and' | 'or'; args: PredicateExpr[] };
type NotNode = { op: 'not'; args: [PredicateExpr] };

function isCompound(e: PredicateExpr): e is Compound {
  const op = (e as { op?: string }).op;
  return op === 'and' || op === 'or';
}

function isNot(e: PredicateExpr): e is NotNode {
  return (e as { op?: string }).op === 'not';
}

export function isLeaf(e: PredicateExpr): boolean {
  const op = (e as { op?: string }).op;
  return op === 'eq' || op === 'in' || op === 'exists';
}

interface Props {
  value: PredicateExpr;
  onChange: (v: PredicateExpr) => void;
  refSources: RefSource[];
  schemaByRef?: (ref: RefExpr) => unknown;
  /** Internal: whether this node is the root of the tree (no delete/wrap controls). */
  isRoot?: boolean;
}

function wrap(kind: 'and' | 'or' | 'not', e: PredicateExpr): PredicateExpr {
  if (kind === 'not') {
    return { op: 'not', args: [e] } as unknown as PredicateExpr;
  }
  return { op: kind, args: [e] };
}

export function AdvancedAstBuilder({
  value,
  onChange,
  refSources,
  schemaByRef,
  isRoot = true,
}: Props) {
  // NOT node
  if (isNot(value)) {
    const inner = value.args[0];
    return (
      <div className="rounded-md border border-wr-border bg-wr-surface p-2">
        <div className="mb-2 flex items-center gap-2">
          <span className="rounded bg-wr-elevated px-2 py-0.5 text-xs font-medium uppercase text-wr-text-muted">
            NOT
          </span>
          <button
            type="button"
            aria-label="Unwrap NOT"
            onClick={() => onChange(inner)}
            className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
          >
            Unwrap NOT
          </button>
          {!isRoot && (
            <>
              <button
                type="button"
                aria-label="Wrap in AND"
                onClick={() => onChange(wrap('and', value))}
                className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
              >
                Wrap in AND
              </button>
              <button
                type="button"
                aria-label="Wrap in OR"
                onClick={() => onChange(wrap('or', value))}
                className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
              >
                Wrap in OR
              </button>
            </>
          )}
        </div>
        <AdvancedAstBuilder
          value={inner}
          onChange={(next) =>
            onChange({ op: 'not', args: [next] } as unknown as PredicateExpr)
          }
          refSources={refSources}
          schemaByRef={schemaByRef}
          isRoot={false}
        />
      </div>
    );
  }

  // Compound AND / OR
  if (isCompound(value)) {
    const otherKind = value.op === 'and' ? 'or' : 'and';
    return (
      <div className="rounded-md border border-wr-border bg-wr-surface p-2">
        <div className="mb-2 flex items-center gap-2">
          <span className="rounded bg-wr-elevated px-2 py-0.5 text-xs font-medium uppercase text-wr-text-muted">
            {value.op}
          </span>
          <button
            type="button"
            aria-label={`Change to ${otherKind.toUpperCase()}`}
            onClick={() =>
              onChange({ op: otherKind, args: value.args } as PredicateExpr)
            }
            className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
          >
            Change to {otherKind.toUpperCase()}
          </button>
          {!isRoot && (
            <>
              <button
                type="button"
                aria-label="Wrap in NOT"
                onClick={() => onChange(wrap('not', value))}
                className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
              >
                Wrap in NOT
              </button>
            </>
          )}
        </div>

        <ul className="flex flex-col gap-2">
          {value.args.map((child, i) => (
            <li key={i} className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Wrap in AND"
                  onClick={() => {
                    const nextArgs = value.args.slice();
                    nextArgs[i] = wrap('and', child);
                    onChange({ op: value.op, args: nextArgs });
                  }}
                  className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
                >
                  Wrap in AND
                </button>
                <button
                  type="button"
                  aria-label="Wrap in OR"
                  onClick={() => {
                    const nextArgs = value.args.slice();
                    nextArgs[i] = wrap('or', child);
                    onChange({ op: value.op, args: nextArgs });
                  }}
                  className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
                >
                  Wrap in OR
                </button>
                <button
                  type="button"
                  aria-label="Wrap in NOT"
                  onClick={() => {
                    const nextArgs = value.args.slice();
                    nextArgs[i] = wrap('not', child);
                    onChange({ op: value.op, args: nextArgs });
                  }}
                  className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
                >
                  Wrap in NOT
                </button>
                <button
                  type="button"
                  aria-label="Delete clause"
                  onClick={() => {
                    const nextArgs = value.args.slice();
                    nextArgs.splice(i, 1);
                    onChange({ op: value.op, args: nextArgs });
                  }}
                  className="rounded border border-wr-border bg-wr-surface px-2 py-0.5 text-xs text-wr-text hover:bg-wr-elevated"
                >
                  Delete clause
                </button>
              </div>
              <AdvancedAstBuilder
                value={child}
                onChange={(next) => {
                  const nextArgs = value.args.slice();
                  nextArgs[i] = next;
                  onChange({ op: value.op, args: nextArgs });
                }}
                refSources={refSources}
                schemaByRef={schemaByRef}
                isRoot={false}
              />
            </li>
          ))}
        </ul>

        <div className="mt-2">
          <button
            type="button"
            aria-label="Add clause"
            onClick={() => {
              // New empty clause — represented as an empty eq-in-progress.
              // We use an empty "and" with no args as a placeholder that
              // SimplePredicate can fill on Apply. To keep leaves valid,
              // we add an exists-less stub: an empty and with no args would
              // be weird; instead we push an empty-shaped eq placeholder.
              const placeholder = {
                op: 'and',
                args: [],
              } as unknown as PredicateExpr;
              onChange({
                op: value.op,
                args: [...value.args, placeholder],
              });
            }}
            className="rounded border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated"
          >
            + Add clause
          </button>
        </div>
      </div>
    );
  }

  // Leaf — reuse SimplePredicate (value prop currently ignored by SimplePredicate;
  // it stays a controlled-ish editor that applies via onChange.)
  return (
    <div className="flex flex-col gap-1">
      <SimplePredicate
        value={value}
        onChange={onChange}
        refSources={refSources}
      />
    </div>
  );
}

export default AdvancedAstBuilder;
