import type { RouterContext } from '../types';

/**
 * Type-safe accessor for RouterContext fields by string key.
 * Replaces unsafe `(context as unknown as Record<string, unknown>)[key]` casts
 * used in QuickActionToolbar and ToolParamForm.
 *
 * Returns the value at `key` if it exists on the context object, or `undefined`.
 */
export function getContextValue(context: RouterContext, key: string): unknown {
  if (key in context) {
    return context[key as keyof RouterContext];
  }
  return undefined;
}
