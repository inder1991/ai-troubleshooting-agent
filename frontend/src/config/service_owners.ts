/**
 * Static service → owning-team lookup used by Patient Zero's ownership
 * line in the War Room left panel.
 *
 * This file is an MVP. The long-term plan is a backend field
 * (`patient_zero.owning_team`) populated from an ops-managed service
 * registry; once that lands, this static map can be deprecated in favor
 * of the backend-provided value. See
 * docs/design/left-panel-editorial.md for the rollout note.
 *
 * Keys are the service identifier the backend emits as
 * `patient_zero.service`. Typically a kubernetes service name.
 *
 * `slack` is an optional channel that, when present, makes the team
 * name clickable — desktop Slack deep-link first, web fallback second.
 * `pagerduty` is reserved for a future "page oncall" affordance.
 *
 * Absence is a signal. If a service is not in this map, the ownership
 * line simply does not render — never an "owner unknown" placeholder.
 */

export interface ServiceOwner {
  team: string;
  slack?: string;        // channel name including leading "#", e.g. "#team-payments"
  pagerduty?: string;    // service-key in PagerDuty, reserved
}

// Seed list. Extend as new services come online. Lowercase service names
// only — the lookup normalises to lowercase before comparing.
export const SERVICE_OWNERS: Record<string, ServiceOwner> = {
  'checkout-service':   { team: 'payments-platform',  slack: '#team-payments' },
  'payments-api':       { team: 'payments-platform',  slack: '#team-payments' },
  'auth-service':       { team: 'identity',           slack: '#team-identity' },
  'inventory-service':  { team: 'commerce',           slack: '#team-commerce' },
  'notification-svc':   { team: 'platform',           slack: '#team-platform' },
};

export function lookupOwner(service: string | undefined | null): ServiceOwner | null {
  if (!service) return null;
  const key = service.toLowerCase();
  return SERVICE_OWNERS[key] ?? null;
}

/**
 * Build an outbound URL for the team's Slack channel. Desktop-first: the
 * `slack://` scheme opens Slack native if installed. A plain web fallback
 * URL is also returned for the HREF so it works in any browser.
 *
 * Note: without knowing the workspace, `slack://channel?team=&id=` isn't
 * reliable. We use the public redirect URL, which Slack's own clients
 * handle gracefully.
 */
export function slackUrlFor(channel: string): string {
  const stripped = channel.replace(/^#/, '');
  return `https://slack.com/app_redirect?channel=${encodeURIComponent(stripped)}`;
}
