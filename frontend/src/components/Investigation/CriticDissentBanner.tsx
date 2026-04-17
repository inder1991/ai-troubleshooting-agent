import type { CriticDissentIndicator } from './cards/AgentFindingCard';

export interface CriticDissentBannerProps {
  dissent: CriticDissentIndicator | null | undefined;
}

/**
 * CriticDissentBanner — shown at the top of Investigator when the winning
 * finding's advocate/challenger/judge verdicts don't all agree. The idea:
 * users deserve a louder signal than a per-card icon when the *winning*
 * hypothesis is contested.
 *
 * Renders nothing when verdicts agree or when no dissent data is present.
 */
export function CriticDissentBanner({ dissent }: CriticDissentBannerProps) {
  if (!dissent) return null;
  const allAgree =
    dissent.advocate_verdict === dissent.challenger_verdict &&
    dissent.advocate_verdict === dissent.judge_verdict;
  if (allAgree) return null;

  return (
    <div
      data-testid="critic-dissent-banner"
      className="w-full border border-wr-amber/40 bg-wr-amber/10 text-wr-amber px-3 py-2 rounded-md flex items-start gap-2 text-sm"
    >
      <span
        className="material-symbols-outlined text-base leading-5"
        aria-hidden
      >
        alt_route
      </span>
      <div className="flex-1">
        <div className="font-medium">Critics disagreed on the winning hypothesis</div>
        <div className="mt-1 text-xs font-mono grid grid-cols-3 gap-x-4 gap-y-0.5">
          <span>
            advocate: <span className="font-bold">{dissent.advocate_verdict}</span>
          </span>
          <span>
            challenger: <span className="font-bold">{dissent.challenger_verdict}</span>
          </span>
          <span>
            judge: <span className="font-bold">{dissent.judge_verdict}</span>
          </span>
        </div>
        {dissent.summary && (
          <div className="mt-1 text-xs text-wr-amber/90">{dissent.summary}</div>
        )}
      </div>
    </div>
  );
}
