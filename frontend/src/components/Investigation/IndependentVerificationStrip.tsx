/**
 * IndependentVerificationStrip — cross-source pins from the critic retriever.
 *
 * Rendered as a dashed-border strip between primary findings and lower-
 * priority findings. The visual distinction matters: these pins came from
 * tools the originating agent did NOT use, so they're independent
 * verification — not another rehash of the same data source.
 *
 * Renders nothing when no retriever pins are available, so the stack
 * stays compact when the ensemble didn't run cross-source verification.
 */
export interface VerificationPin {
  tool_name: string;
  query?: string;
  query_timestamp?: string;
  raw_value?: string;
  claim?: string;
}

export interface IndependentVerificationStripProps {
  pins: VerificationPin[];
}

export function IndependentVerificationStrip({
  pins,
}: IndependentVerificationStripProps) {
  if (!pins || pins.length === 0) return null;

  return (
    <div
      data-testid="indep-verif-strip"
      className="w-full border border-dashed border-wr-border-strong/60 bg-wr-bg/40 rounded-md px-3 py-2 my-2"
    >
      <div className="flex items-center gap-2 mb-1.5 text-body-xs text-slate-400 uppercase tracking-wider">
        <span
          className="material-symbols-outlined text-[14px]"
          aria-hidden
        >
          search
        </span>
        Independent verification
        <span className="ml-auto font-mono text-[10px] text-slate-500">
          {pins.length} {pins.length === 1 ? 'pin' : 'pins'}
        </span>
      </div>
      <ul className="space-y-1">
        {pins.map((p, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-xs text-slate-300"
          >
            <span
              className="font-mono text-slate-400 min-w-[120px] truncate"
              title={p.tool_name}
            >
              {p.tool_name}
            </span>
            <span className="flex-1 min-w-0 truncate" title={p.claim || p.raw_value}>
              {p.claim || p.raw_value || p.query}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
