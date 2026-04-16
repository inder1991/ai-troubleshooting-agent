// Enumerate dotted JSON-pointer-ish paths from a JSON-schema-ish object.
// Objects use `.key` descent; arrays use `[*]` marker. Missing / non-object
// schemas return [].
export function listPaths(schema: unknown, prefix = ''): string[] {
  if (!schema || typeof schema !== 'object') return [];
  const s = schema as {
    properties?: Record<string, unknown>;
    items?: unknown;
  };
  const out: string[] = [];
  if (s.properties && typeof s.properties === 'object') {
    for (const [k, sub] of Object.entries(s.properties)) {
      const p = prefix ? `${prefix}.${k}` : k;
      out.push(p);
      out.push(...listPaths(sub, p));
    }
  }
  if (s.items) {
    const arrPrefix = prefix ? `${prefix}[*]` : '[*]';
    out.push(...listPaths(s.items, arrPrefix));
  }
  return out;
}
