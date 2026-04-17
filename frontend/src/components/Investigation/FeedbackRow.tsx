import { useState } from 'react';

/**
 * FeedbackRow — bottom-of-Investigator outcome labelling.
 *
 * POSTs to /api/v4/investigations/{runId}/feedback (Task 2.5). The request
 * is idempotent on (run_id, submitter) server-side; this component
 * additionally hides the form after a successful submit so a user can't
 * visually re-submit and get a "replay" 200 they'd be confused by.
 */
export interface FeedbackSubmitPayload {
  runId: string;
  wasCorrect: boolean;
  actualRootCause: string;
}

export interface FeedbackRowProps {
  runId: string;
  submit: (p: FeedbackSubmitPayload) => Promise<{ ok: boolean }>;
}

type Verdict = 'correct' | 'wrong' | null;

export function FeedbackRow({ runId, submit }: FeedbackRowProps) {
  const [verdict, setVerdict] = useState<Verdict>(null);
  const [rootCause, setRootCause] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (done) {
    return (
      <div className="px-4 py-3 border-t border-wr-border/40 text-sm text-wr-emerald">
        ✓ Thanks for the feedback — priors updated for the winning agents.
      </div>
    );
  }

  const canSubmit = verdict !== null && !submitting;

  const handleSubmit = async () => {
    if (verdict === null) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await submit({
        runId,
        wasCorrect: verdict === 'correct',
        actualRootCause: rootCause,
      });
      if (res.ok) {
        setDone(true);
      } else {
        setError("Couldn't submit — try again.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't submit.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="px-4 py-3 border-t border-wr-border/40 flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-wr-muted uppercase tracking-wider">
        Was this investigation correct?
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setVerdict('correct')}
          className={`px-3 py-1 rounded-md text-sm border transition ${
            verdict === 'correct'
              ? 'border-wr-emerald/60 bg-wr-emerald/10 text-wr-emerald'
              : 'border-wr-border/60 text-wr-text hover:border-wr-emerald/40'
          }`}
        >
          👍 Correct
        </button>
        <button
          type="button"
          onClick={() => setVerdict('wrong')}
          className={`px-3 py-1 rounded-md text-sm border transition ${
            verdict === 'wrong'
              ? 'border-wr-red/60 bg-wr-red/10 text-wr-red'
              : 'border-wr-border/60 text-wr-text hover:border-wr-red/40'
          }`}
        >
          👎 Wrong
        </button>
        <label className="flex-1 flex items-center gap-2 min-w-[200px]">
          <span className="sr-only">Actual root cause (optional)</span>
          <input
            type="text"
            placeholder="Actual root cause (optional)"
            aria-label="Actual root cause"
            value={rootCause}
            onChange={(e) => setRootCause(e.target.value)}
            className="flex-1 bg-wr-bg/40 border border-wr-border/60 rounded px-2 py-1 text-sm"
          />
        </label>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="px-3 py-1 rounded-md text-sm border border-wr-amber/60 bg-wr-amber/10 text-wr-amber disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </div>
      {error && (
        <div className="text-xs text-wr-red" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
