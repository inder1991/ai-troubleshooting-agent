/**
 * RetestVerdictBlock — shows the result of re-running the originating tool
 * after a fix was applied (Task 4.20 backend RetestScheduler).
 *
 * Verdicts:
 *  - symptom_resolved: emerald, "original -> current" delta.
 *  - symptom_persists: red, "no change" call-out.
 *  - insufficient: amber, "not enough signal to decide".
 */
export type RetestVerdict = 'symptom_resolved' | 'symptom_persists' | 'insufficient';

export interface RetestPayload {
  verdict: RetestVerdict;
  checked_at: string;
  original_value: string;
  current_value: string;
}

export interface RetestVerdictBlockProps {
  retest: RetestPayload | null | undefined;
}

const TONE: Record<RetestVerdict, { label: string; cls: string }> = {
  symptom_resolved: {
    label: 'Symptom resolved',
    cls: 'border-wr-emerald/40 bg-wr-emerald/10 text-wr-emerald',
  },
  symptom_persists: {
    label: 'Symptom persists',
    cls: 'border-wr-red/40 bg-wr-red/10 text-wr-red',
  },
  insufficient: {
    label: 'Insufficient signal',
    cls: 'border-wr-amber/40 bg-wr-amber/10 text-wr-amber',
  },
};

export function RetestVerdictBlock({ retest }: RetestVerdictBlockProps) {
  if (!retest) return null;
  const tone = TONE[retest.verdict];
  return (
    <div
      data-testid="retest-verdict-block"
      className={`border rounded-md px-3 py-2 text-sm ${tone.cls}`}
    >
      <div className="flex items-center gap-2">
        <span
          className="material-symbols-outlined text-[14px]"
          aria-hidden
        >
          {retest.verdict === 'symptom_resolved'
            ? 'check_circle'
            : retest.verdict === 'symptom_persists'
              ? 'cancel'
              : 'help'}
        </span>
        <span className="font-medium">{tone.label}</span>
        <span className="ml-auto text-xs opacity-70 font-mono">
          {retest.checked_at}
        </span>
      </div>
      <div className="mt-1 text-xs font-mono">
        {retest.original_value} → {retest.current_value}
      </div>
    </div>
  );
}
