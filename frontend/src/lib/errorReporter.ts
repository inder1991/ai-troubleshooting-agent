// Q16 — frontend error reporter wrapper.
//
// Today: thin wrapper around console.warn/error with a beforeSend hook
// that scrubs secret-shaped strings (Q13). Production deployment swaps
// the backend transport for Sentry/Rollbar/etc. without touching call
// sites.

const SECRET_PATTERNS: RegExp[] = [
  /AKIA[0-9A-Z]{16}/g,
  /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g,
  /(api[_-]?key|secret|password|token)["']?\s*[:=]\s*["']([^"']{8,})["']/gi,
];

function redact(text: string): string {
  let out = text;
  for (const pattern of SECRET_PATTERNS) {
    out = out.replace(pattern, "[REDACTED]");
  }
  return out;
}

export interface ErrorReportContext {
  event: string;
  route?: string;
  session_id?: string;
  [key: string]: unknown;
}

export const errorReporter = {
  captureMessage(message: string, context: ErrorReportContext): void {
    const safe = redact(message);
    // Until a real SDK lands, emit to console.warn — but ESLint
    // no-console rule is configured to allow console.warn/error
    // when called via this wrapper (see Q16 logging policy).
    // eslint-disable-next-line no-console
    console.warn(JSON.stringify({ level: "WARN", message: safe, ...context }));
  },

  captureException(err: unknown, context: ErrorReportContext): void {
    const message = err instanceof Error ? err.message : String(err);
    const safe = redact(message);
    // eslint-disable-next-line no-console
    console.error(
      JSON.stringify({
        level: "ERROR",
        message: safe,
        stack: err instanceof Error ? err.stack : undefined,
        ...context,
      }),
    );
  },
};
