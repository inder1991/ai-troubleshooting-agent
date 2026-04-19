import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  RegionPortalsProvider,
  useRegionPortals,
} from '../RegionPortalsContext';

function Consumer() {
  const v = useRegionPortals();
  return (
    <>
      <div data-testid="evidence-null">
        {v.evidenceRef.current ? 'yes' : 'no'}
      </div>
    </>
  );
}

describe('RegionPortalsContext', () => {
  it('exposes inert refs when rendered outside provider', () => {
    const { getByTestId } = render(<Consumer />);
    expect(getByTestId('evidence-null').textContent).toBe('no');
  });

  it('publishes evidence ref when setEvidenceEl is invoked', () => {
    function Harness() {
      const { setEvidenceEl, evidenceRef } = useRegionPortals();
      return (
        <>
          <div data-testid="evidence-host" ref={setEvidenceEl} />
          <div data-testid="evidence-present">
            {evidenceRef.current ? 'mounted' : 'empty'}
          </div>
        </>
      );
    }
    const { getByTestId } = render(
      <RegionPortalsProvider>
        <Harness />
      </RegionPortalsProvider>,
    );
    expect(getByTestId('evidence-present').textContent).toBe('mounted');
  });

  it('publishes navigator + gutter + investigator refs independently', () => {
    function Harness() {
      const {
        setEvidenceEl,
        setNavigatorEl,
        setGutterEl,
        setInvestigatorEl,
        evidenceRef,
        navigatorRef,
        gutterRef,
        investigatorRef,
      } = useRegionPortals();
      return (
        <>
          <div data-testid="e" ref={setEvidenceEl} />
          <div data-testid="n" ref={setNavigatorEl} />
          <div data-testid="g" ref={setGutterEl} />
          <div data-testid="i" ref={setInvestigatorEl} />
          <div data-testid="status">
            {evidenceRef.current ? 'e' : '-'}
            {navigatorRef.current ? 'n' : '-'}
            {gutterRef.current ? 'g' : '-'}
            {investigatorRef.current ? 'i' : '-'}
          </div>
        </>
      );
    }
    const { getByTestId } = render(
      <RegionPortalsProvider>
        <Harness />
      </RegionPortalsProvider>,
    );
    expect(getByTestId('status').textContent).toBe('engi');
  });
});
