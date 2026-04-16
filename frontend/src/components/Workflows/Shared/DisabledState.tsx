import { useFeatureFlags } from '../../../contexts/FeatureFlagsContext';

/**
 * Rendered when the workflows feature is disabled (backend returned 404
 * on the probe). Offers a Retry button that re-runs the probe so the UI
 * can recover from partial deploys or mid-session flag flips without a
 * full page reload.
 */
export function DisabledState() {
  const { retry, loading } = useFeatureFlags();
  return (
    <div
      role="status"
      className="min-h-[60vh] w-full flex items-center justify-center px-6 py-10"
    >
      <div className="max-w-md w-full rounded-lg border border-wr-border bg-wr-surface p-8 text-center shadow-sm">
        <h2 className="text-lg font-display font-semibold text-wr-text mb-2">
          Workflows unavailable
        </h2>
        <p className="text-sm text-wr-text-muted mb-6">
          Workflows feature is disabled in this environment.
        </p>
        <button
          type="button"
          onClick={() => {
            void retry();
          }}
          disabled={loading}
          className="inline-flex items-center justify-center rounded-md border border-wr-border bg-wr-accent px-4 py-2 text-sm font-medium text-wr-on-accent transition-colors hover:bg-wr-accent-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-wr-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Checking…' : 'Retry'}
        </button>
      </div>
    </div>
  );
}

export default DisabledState;
