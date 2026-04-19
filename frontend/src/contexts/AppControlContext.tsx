import React, { createContext, useContext, useMemo, useState } from 'react';

/**
 * AppControlContext (PR 2)
 *
 * Centralizes the "Assume Control" / manual-override state that the
 * future app header toggle will expose. Built now so the banner region
 * can read it on day one — when the real toggle lands in a later PR,
 * only the header emits to this context and nothing in the War Room
 * needs to change.
 *
 * Default: autonomous (agents running as normal). When
 * `isManualOverride` is true:
 *   · Freshness row's leading clause flips to "⏸ manual override"
 *   · Phase narrative becomes "Awaiting operator input."
 *   · Polling cadence should be relaxed by the consumer (the hook
 *     `useRefetchCadence()` will read this once that polling refactor
 *     lands in PR 7).
 */

interface AppControlValue {
  isManualOverride: boolean;
  setManualOverride: (b: boolean) => void;
}

const Ctx = createContext<AppControlValue | null>(null);

export const AppControlProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [isManualOverride, setManualOverride] = useState(false);
  const value = useMemo(
    () => ({ isManualOverride, setManualOverride }),
    [isManualOverride],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export function useAppControl(): AppControlValue {
  const v = useContext(Ctx);
  if (!v) {
    // Sensible default when rendered outside the provider — the banner
    // still renders in autonomous mode rather than crashing.
    return { isManualOverride: false, setManualOverride: () => {} };
  }
  return v;
}
