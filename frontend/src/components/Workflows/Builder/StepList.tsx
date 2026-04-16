import { useEffect, useRef, useState } from 'react';
import type {
  MappingExpr,
  PredicateExpr,
  RefExpr,
  StepSpec,
  TransformExpr,
  LiteralExpr,
} from '../../../types';
import type { ValidationError } from './builderTypes';
import { StepSummaryRow } from './StepSummaryRow';

interface Props {
  steps: StepSpec[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onReorder: (newSteps: StepSpec[]) => void;
  errorsByStepId?: Record<string, ValidationError[]>;
}

function isRef(v: unknown): v is RefExpr {
  return !!v && typeof v === 'object' && 'ref' in (v as Record<string, unknown>);
}
function isLiteral(v: unknown): v is LiteralExpr {
  return !!v && typeof v === 'object' && 'literal' in (v as Record<string, unknown>);
}
function isTransform(v: unknown): v is TransformExpr {
  return (
    !!v &&
    typeof v === 'object' &&
    'op' in (v as Record<string, unknown>) &&
    'args' in (v as Record<string, unknown>)
  );
}

function collectFromMapping(m: MappingExpr | undefined, out: Set<string>): void {
  if (!m) return;
  if (isRef(m)) {
    if (m.ref.from === 'node') out.add(m.ref.node_id);
    return;
  }
  if (isLiteral(m)) return;
  if (isTransform(m)) {
    for (const a of m.args ?? []) collectFromMapping(a, out);
  }
}

function collectFromPredicate(
  p: PredicateExpr | undefined,
  out: Set<string>,
): void {
  if (!p) return;
  // predicate nodes carry either left/right, args (array of MappingExpr or PredicateExpr), or arg
  const pp = p as Record<string, unknown>;
  if ('left' in pp) collectFromMapping(pp.left as MappingExpr | undefined, out);
  if ('right' in pp) collectFromMapping(pp.right as MappingExpr | undefined, out);
  if ('arg' in pp) collectFromPredicate(pp.arg as PredicateExpr, out);
  if ('args' in pp && Array.isArray(pp.args)) {
    // args can be MappingExpr[] (for eq/in/exists) or PredicateExpr[] (and/or)
    const op = (pp.op as string) ?? '';
    if (op === 'and' || op === 'or') {
      for (const a of pp.args as PredicateExpr[]) collectFromPredicate(a, out);
    } else {
      for (const a of pp.args as MappingExpr[]) collectFromMapping(a, out);
    }
  }
}

/** Pure helper: returns node_ids referenced by this step via inputs + when. */
export function extractStepDependencies(step: StepSpec): string[] {
  const out = new Set<string>();
  for (const v of Object.values(step.inputs ?? {})) {
    collectFromMapping(v, out);
  }
  collectFromPredicate(step.when, out);
  return Array.from(out);
}

/** Validate an ordering: no step may appear before a step it references. */
function findBrokenDependency(
  ordered: StepSpec[],
): { consumer: string; dependency: string } | null {
  const index: Record<string, number> = {};
  ordered.forEach((s, i) => {
    index[s.id] = i;
  });
  for (const step of ordered) {
    const deps = extractStepDependencies(step);
    for (const dep of deps) {
      if (!(dep in index)) continue; // dep refers to a step not in list; ignore
      if (index[dep] >= index[step.id]) {
        return { consumer: step.id, dependency: dep };
      }
    }
  }
  return null;
}

export function StepList({
  steps,
  selectedId,
  onSelect,
  onReorder,
  errorsByStepId,
}: Props) {
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);
  const [overPos, setOverPos] = useState<'before' | 'after'>('before');
  const [error, setError] = useState<string | null>(null);
  // Synchronous mirrors so drop handler can read latest values set
  // within the same event tick (React state updates aren't flushed
  // synchronously between sibling DOM events in jsdom).
  const dragIdxRef = useRef<number | null>(null);
  const overPosRef = useRef<'before' | 'after'>('before');
  const overIdxRef = useRef<number | null>(null);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 3000);
    return () => clearTimeout(t);
  }, [error]);

  function handleDragStart(e: React.DragEvent, idx: number) {
    dragIdxRef.current = idx;
    setDragIdx(idx);
    try {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(idx));
    } catch {
      /* ignore */
    }
  }

  function handleDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const midpoint = rect.top + rect.height / 2;
    // If clientY is unavailable (jsdom drag events don't populate it),
    // fall back to reading the value from the dataTransfer "text/y" slot
    // that callers can set; otherwise default to 'before'.
    const hasY = typeof e.clientY === 'number' && !Number.isNaN(e.clientY);
    let pos: 'before' | 'after' = 'before';
    if (hasY) {
      pos = e.clientY < midpoint ? 'before' : 'after';
    } else {
      try {
        const yStr = e.dataTransfer?.getData('text/y');
        if (yStr) {
          const y = Number(yStr);
          if (!Number.isNaN(y)) pos = y < midpoint ? 'before' : 'after';
        }
      } catch {
        /* ignore */
      }
    }
    overIdxRef.current = idx;
    overPosRef.current = pos;
    setOverIdx(idx);
    setOverPos(pos);
  }

  function handleDrop(e: React.DragEvent, idx: number) {
    e.preventDefault();
    const from = dragIdxRef.current ?? dragIdx;
    if (from === null) return;
    // Position is tracked by the most recent dragOver for this row.
    const pos: 'before' | 'after' =
      overIdxRef.current === idx ? overPosRef.current : 'before';

    // Compute target index in the pre-removal list
    let insertAt = pos === 'before' ? idx : idx + 1;
    // Remove source then adjust insertion index if source was before insertion point
    const reordered = steps.slice();
    const [moved] = reordered.splice(from, 1);
    if (from < insertAt) insertAt -= 1;
    reordered.splice(insertAt, 0, moved);

    dragIdxRef.current = null;
    overIdxRef.current = null;
    setDragIdx(null);
    setOverIdx(null);

    if (reordered.every((s, i) => s.id === steps[i]?.id)) {
      // No change
      return;
    }

    const broken = findBrokenDependency(reordered);
    if (broken) {
      setError(
        `Cannot place ${broken.dependency} before its dependency ${broken.consumer}`,
      );
      return;
    }
    onReorder(reordered);
  }

  function handleDragEnd() {
    dragIdxRef.current = null;
    overIdxRef.current = null;
    setDragIdx(null);
    setOverIdx(null);
  }

  return (
    <div className="flex flex-col gap-1" data-testid="step-list">
      {steps.map((step, idx) => {
        const isDropBefore = overIdx === idx && overPos === 'before';
        const isDropAfter = overIdx === idx && overPos === 'after';
        return (
          <div
            key={step.id}
            data-testid="step-row"
            onDragOver={(e) => handleDragOver(e, idx)}
            onDrop={(e) => handleDrop(e, idx)}
            className={
              'flex items-center gap-1 rounded-md ' +
              (isDropBefore ? 'border-t-2 border-wr-accent ' : '') +
              (isDropAfter ? 'border-b-2 border-wr-accent ' : '')
            }
          >
            <span
              data-testid="drag-handle"
              aria-label={`Drag step ${step.id}`}
              draggable
              onDragStart={(e) => handleDragStart(e, idx)}
              onDragEnd={handleDragEnd}
              className="flex h-7 w-5 shrink-0 cursor-grab items-center justify-center text-wr-text-muted hover:text-wr-text"
            >
              <span aria-hidden="true">⋮⋮</span>
            </span>
            <div className="flex-1">
              <StepSummaryRow
                step={step}
                index={idx}
                active={step.id === selectedId}
                onSelect={() => onSelect(step.id)}
                errors={errorsByStepId?.[step.id]}
              />
            </div>
          </div>
        );
      })}

      {error && (
        <div
          role="alert"
          className="mt-1 self-start rounded-full border border-red-500/40 bg-red-500/10 px-3 py-1 text-xs text-red-400"
        >
          {error}
        </div>
      )}
    </div>
  );
}

export default StepList;
