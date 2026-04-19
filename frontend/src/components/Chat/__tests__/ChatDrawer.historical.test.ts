import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

/**
 * PR-G — source-level guard that ChatDrawer:
 *   · Reads useIncidentLifecycle to detect archived sessions.
 *   · Renders the `chat-historical-banner` on historical lifecycles.
 *   · Passes `isHistorical` into ChatInputArea's `disabled` prop so
 *     the textarea + send button gray out.
 *
 * Full render-level testing would require stubbing ChatContext,
 * RegionPortals, InvestigationContext, and useInvestigationTools —
 * the cost exceeds the value for a three-line gate.
 */

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(__dirname, '../ChatDrawer.tsx'),
  'utf8',
);

describe('ChatDrawer historical lockdown (PR-G)', () => {
  it('imports useIncidentLifecycle', () => {
    expect(source).toMatch(
      /useIncidentLifecycle.*from.*IncidentLifecycleContext/,
    );
  });

  it('derives isHistorical from the lifecycle hook', () => {
    expect(source).toMatch(
      /const\s+isHistorical\s*=\s*lifecycle\s*===\s*['"]historical['"]/,
    );
  });

  it('renders a historical banner with testid chat-historical-banner', () => {
    expect(source).toMatch(/data-testid=['"]chat-historical-banner['"]/);
    expect(source).toMatch(/Archived investigation/);
  });

  it('disables ChatInputArea when historical', () => {
    // The textarea + send button must honor the disabled flag when
    // historical, so a restored-from-URL archived session can't accept
    // new chat input.
    expect(source).toMatch(/disabled=\{isSending\s*\|\|\s*isHistorical\}/);
  });

  it('swaps the placeholder to explain why input is disabled', () => {
    expect(source).toMatch(/Chat closed — investigation is archived/);
  });
});
