import type { ReactNode } from 'react';
import { useFeatureFlags } from '../../../contexts/FeatureFlagsContext';
import { DisabledState } from './DisabledState';

interface WorkflowsGuardProps {
  children: ReactNode;
}

/**
 * Route-level guard for the workflows feature.
 *
 * - While the feature-flag probe is in flight: render a lightweight
 *   loading indicator (prevents routing through to child pages that
 *   may themselves fetch on mount).
 * - If the probe resolved with `workflows === false`: render
 *   `<DisabledState />`.
 * - Otherwise: render children.
 */
export function WorkflowsGuard({ children }: WorkflowsGuardProps) {
  const { workflows, loading } = useFeatureFlags();

  if (loading) {
    return (
      <div
        role="status"
        aria-busy="true"
        className="min-h-[60vh] w-full flex items-center justify-center text-sm text-wr-text-muted"
      >
        Loading…
      </div>
    );
  }

  if (!workflows) {
    return <DisabledState />;
  }

  return <>{children}</>;
}

export default WorkflowsGuard;
