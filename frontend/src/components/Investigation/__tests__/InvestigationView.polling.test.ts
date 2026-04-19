import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

/**
 * PR-G — source-level guard that InvestigationView does not keep
 * polling /status + /findings on historical incidents.
 *
 * Testing the actual useEffect behavior would require mocking the
 * full context stack (ChatContext, CampaignContext, InvestigationContext,
 * RegionPortalsContext, IncidentLifecycleContext). A source-level
 * assertion on the specific guards is cheaper and catches the
 * regression we care about: a future refactor that accidentally
 * removes `isHistorical` from the effect dependencies.
 */

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(__dirname, '../InvestigationView.tsx'),
  'utf8',
);

describe('InvestigationView polling gates (PR-G)', () => {
  it('imports deriveLifecycle so it can gate effects without relying on the provider hook', () => {
    expect(source).toMatch(/deriveLifecycle.*from.*IncidentLifecycleContext/);
  });

  it('derives isHistorical from sessionStatus', () => {
    expect(source).toMatch(/const\s+isHistorical\s*=\s*derived\.lifecycle\s*===\s*['"]historical['"]/);
  });

  it('polling interval effect guards on isHistorical', () => {
    // The effect that sets the repeated /status+/findings fetch must
    // early-return when the incident is historical, so background tabs
    // on archived incidents don't burn bandwidth/battery.
    const pollEffect = source.match(
      /fetchSharedData\(\);\s*\n(?:\s*\/\/[^\n]*\n)*\s*if\s*\(isHistorical\)\s*return;/,
    );
    expect(pollEffect).not.toBeNull();
  });

  it('per-second "ago" ticker is suspended on historical', () => {
    // We scan the ticker effect for the guard — it matters because a
    // 1Hz setInterval on an archived incident is pure waste.
    const agoGuard = source.match(
      /useEffect\(\(\)\s*=>\s*\{[^}]*?if\s*\(isHistorical\)\s*return;\s*agoIntervalRef\.current/,
    );
    expect(agoGuard).not.toBeNull();
  });

  it('WebSocket event re-fetch is suspended on historical', () => {
    // Event-driven re-fetch (findings/status on phase_change etc.)
    // also early-returns — otherwise WS replay could fire a fresh
    // /findings call for a closed investigation.
    expect(source).toMatch(/if\s*\(isHistorical\)\s*return;\s*let relevant/);
  });

  // ── PR-H: a11y landmarks ────────────────────────────────────────

  it('wraps each War Room region with role=region + aria-labelledby (PR-H)', () => {
    // Each column (Investigator, Evidence, Navigator) must be a
    // <section role="region"> with an sr-only heading, so screen-reader
    // regions rotor lists them as first-class jump targets.
    expect(source).toMatch(/aria-labelledby=['"]wr-region-label-investigator['"]/);
    expect(source).toMatch(/aria-labelledby=['"]wr-region-label-evidence['"]/);
    expect(source).toMatch(/aria-labelledby=['"]wr-region-label-navigator['"]/);
    expect(source).toMatch(/id=['"]wr-region-label-investigator['"]/);
    expect(source).toMatch(/id=['"]wr-region-label-evidence['"]/);
    expect(source).toMatch(/id=['"]wr-region-label-navigator['"]/);
  });

  it('uses semantic <section> (not <div>) for the region wrappers', () => {
    // Grep that the role=region attribute sits on a section element
    // so the underlying semantic role is correct even if aria-labelledby
    // is stripped by a future refactor.
    const investigatorSection = source.match(
      /<section[^>]*wr-region-investigator[^>]*role=['"]region['"]/s,
    );
    expect(investigatorSection).not.toBeNull();
  });

  it('keeps the initial fetch so deep-links still load data', () => {
    // Critical: we DO want the first fetch so a user opening an
    // archived incident sees its findings — just not the recurring
    // interval. The effect body must still call fetchSharedData()
    // once before the historical early-return.
    const initialFetch = source.match(
      /useEffect\(\(\)\s*=>\s*\{\s*\/\/[^\n]*\n(?:\s*\/\/[^\n]*\n)*\s*fetchSharedData\(\);\s*\n\s*if\s*\(isHistorical\)\s*return;/,
    );
    expect(initialFetch).not.toBeNull();
  });
});
