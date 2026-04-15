import type { PredicateExpr, RefExpr } from '../../../types';

const MAX_LEN = 80;

function truncate(s: string): string {
  if (s.length <= MAX_LEN) return s;
  return s.slice(0, MAX_LEN - 1) + '…';
}

function isRefExpr(v: unknown): v is RefExpr {
  return (
    typeof v === 'object' &&
    v !== null &&
    'ref' in (v as Record<string, unknown>)
  );
}

function isLiteral(v: unknown): v is { literal: unknown } {
  return (
    typeof v === 'object' &&
    v !== null &&
    'literal' in (v as Record<string, unknown>)
  );
}

export function refLabel(ref: RefExpr): string {
  const r = ref.ref;
  if (r.from === 'input') return `input.${r.path}`;
  if (r.from === 'env') return `env.${r.path}`;
  // node
  const nodeId = (r as { node_id: string }).node_id;
  let path = r.path;
  if (path.startsWith('output.')) path = path.slice('output.'.length);
  else if (path === 'output') path = '';
  return path ? `${nodeId}.${path}` : nodeId;
}

function argLabel(a: unknown): string {
  if (isRefExpr(a)) return refLabel(a);
  if (isLiteral(a)) return JSON.stringify(a.literal);
  return '';
}

function summarize(expr: PredicateExpr): string {
  const op = (expr as { op?: string }).op;
  const args = (expr as { args?: unknown[] }).args ?? [];

  switch (op) {
    case 'eq': {
      // args[0] is ref, args[1] is literal
      const left = args[0];
      const right = args[1];
      const leftLabel = isRefExpr(left) ? refLabel(left) : argLabel(left);
      const rightLabel = argLabel(right);
      return `if ${leftLabel} == ${rightLabel}`;
    }
    case 'in': {
      // args[0] is literal, args[1] is ref
      const lit = args[0];
      const ref = args[1];
      const refL = isRefExpr(ref) ? refLabel(ref) : argLabel(ref);
      return `if ${refL} contains ${argLabel(lit)}`;
    }
    case 'exists': {
      const ref = args[0];
      const refL = isRefExpr(ref) ? refLabel(ref) : argLabel(ref);
      return `if ${refL} exists`;
    }
    case 'not': {
      const inner = args[0] as PredicateExpr | undefined;
      if (!inner) return '';
      return `not (${summarize(inner)})`;
    }
    case 'and':
    case 'or': {
      const parts = (args as PredicateExpr[])
        .map((a) => summarize(a))
        .filter(Boolean);
      if (parts.length === 0) return '';
      return `(${parts.join(` ${op.toUpperCase()} `)})`;
    }
    default:
      return '';
  }
}

export function humanTriggerSummary(expr: PredicateExpr | undefined): string {
  if (!expr) return '';
  return truncate(summarize(expr));
}
