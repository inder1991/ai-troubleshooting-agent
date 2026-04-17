/**
 * Normalize an unknown error into a human-readable message.
 *
 * Handles:
 *  - FastAPI-style `{ detail: string }` responses
 *  - Nested `{ detail: { message: string } }` responses
 *  - Standard `Error` instances (uses `.message`)
 *  - Everything else falls back to the provided `fallback` string
 */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (err != null && typeof err === 'object') {
    const obj = err as Record<string, unknown>;

    // FastAPI { detail: "..." }
    if (typeof obj.detail === 'string') {
      return obj.detail;
    }

    // Nested { detail: { message: "..." } }
    if (
      obj.detail != null &&
      typeof obj.detail === 'object' &&
      typeof (obj.detail as Record<string, unknown>).message === 'string'
    ) {
      return (obj.detail as Record<string, unknown>).message as string;
    }
  }

  // Standard Error
  if (err instanceof Error && err.message) {
    return err.message;
  }

  return fallback;
}
