// Frozen set of UI-exposed predicate operators. Comparison ops (gt/gte/lt/lte)
// are intentionally excluded — see Phase 3 plan Task 11.
export const FROZEN_OPS = [
  'eq',
  'neq',
  'contains',
  'not_contains',
  'exists',
  'not_exists',
] as const;

export type SimpleOp = (typeof FROZEN_OPS)[number];

export function isUnaryOp(op: SimpleOp): boolean {
  return op === 'exists' || op === 'not_exists';
}

export type FieldType = 'string' | 'number' | 'integer' | 'boolean' | 'unknown';

export function opsForFieldType(t: FieldType): SimpleOp[] {
  const unary: SimpleOp[] = ['exists', 'not_exists'];
  if (t === 'boolean') return ['eq', 'neq', ...unary];
  if (t === 'string') return ['eq', 'neq', 'contains', 'not_contains', ...unary];
  // number / integer / unknown: no comparison ops (frozen). Allow eq/neq + unary.
  if (t === 'number' || t === 'integer') return ['eq', 'neq', ...unary];
  // unknown: expose the full palette
  return ['eq', 'neq', 'contains', 'not_contains', ...unary];
}
