import React, { createContext, useContext, useRef, useCallback } from 'react';

/**
 * RegionPortalsContext (PR 3 of the War Room grid-shell migration)
 *
 * Publishes DOM-element refs for each grid region so drawers can
 * portal INTO the region they thematically belong to, rather than
 * floating over the viewport. Consumers:
 *
 *   · ChatDrawer      → navigator region (occupies the navigator column)
 *   · TelescopeV2     → evidence region  (capped inside evidence column)
 *   · SurgicalTelescope → evidence region (same contract)
 *   · LedgerTriggerTab → gutter rail
 *
 * The provider stores refs via useRef + callback-ref so consumers can
 * mount once the target element is attached to the DOM. Callers hand
 * the callback ref to the grid-region div (<div ref={setEvidenceRef}/>).
 */

export type Region = 'investigator' | 'evidence' | 'navigator' | 'gutter';

interface RegionPortalsValue {
  /** Mount targets — consumed by PaneDrawer's `mountInto` prop. */
  evidenceRef: React.RefObject<HTMLElement | null>;
  navigatorRef: React.RefObject<HTMLElement | null>;
  investigatorRef: React.RefObject<HTMLElement | null>;
  gutterRef: React.RefObject<HTMLElement | null>;
  /** Callback refs for the region <div>s to register themselves. */
  setEvidenceEl: (el: HTMLElement | null) => void;
  setNavigatorEl: (el: HTMLElement | null) => void;
  setInvestigatorEl: (el: HTMLElement | null) => void;
  setGutterEl: (el: HTMLElement | null) => void;
}

const Ctx = createContext<RegionPortalsValue | null>(null);

export const RegionPortalsProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const evidenceRef = useRef<HTMLElement | null>(null);
  const navigatorRef = useRef<HTMLElement | null>(null);
  const investigatorRef = useRef<HTMLElement | null>(null);
  const gutterRef = useRef<HTMLElement | null>(null);
  // Force re-render of consumers when a region element is first
  // attached so PaneDrawer Portals see a non-null container.
  const [, setVersion] = React.useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  const setEvidenceEl = useCallback(
    (el: HTMLElement | null) => {
      evidenceRef.current = el;
      bump();
    },
    [bump],
  );
  const setNavigatorEl = useCallback(
    (el: HTMLElement | null) => {
      navigatorRef.current = el;
      bump();
    },
    [bump],
  );
  const setInvestigatorEl = useCallback(
    (el: HTMLElement | null) => {
      investigatorRef.current = el;
      bump();
    },
    [bump],
  );
  const setGutterEl = useCallback(
    (el: HTMLElement | null) => {
      gutterRef.current = el;
      bump();
    },
    [bump],
  );

  return (
    <Ctx.Provider
      value={{
        evidenceRef,
        navigatorRef,
        investigatorRef,
        gutterRef,
        setEvidenceEl,
        setNavigatorEl,
        setInvestigatorEl,
        setGutterEl,
      }}
    >
      {children}
    </Ctx.Provider>
  );
};

export function useRegionPortals(): RegionPortalsValue {
  const v = useContext(Ctx);
  if (!v) {
    // Fall back to inert refs so consumer code doesn't crash when
    // rendered outside the grid (tests, storybooks).
    const inert: React.RefObject<HTMLElement | null> = { current: null };
    return {
      evidenceRef: inert,
      navigatorRef: inert,
      investigatorRef: inert,
      gutterRef: inert,
      setEvidenceEl: () => {},
      setNavigatorEl: () => {},
      setInvestigatorEl: () => {},
      setGutterEl: () => {},
    };
  }
  return v;
}
