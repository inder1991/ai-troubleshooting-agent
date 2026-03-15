/**
 * Shared color constants for capability types and agent roles.
 * Every color has a semantic purpose — no decoration.
 */

// Capability type → accent color (used on feed rows, session cards, capability buttons)
export const CAPABILITY_COLORS: Record<string, string> = {
  troubleshoot_app: '#e09f3e',       // Amber gold — primary
  database_diagnostics: '#8b5cf6',   // Violet
  cluster_diagnostics: '#10b981',    // Emerald
  network_troubleshooting: '#0ea5e9', // Sky blue
  pr_review: '#3b82f6',             // Blue
  github_issue_fix: '#f43f5e',       // Rose
};

// Agent role → accent color (used on agent card icons, role headers)
export const ROLE_COLORS: Record<string, string> = {
  orchestrator: '#e09f3e',   // Amber — command & control
  analysis: '#0ea5e9',       // Sky — data investigation
  domain_expert: '#10b981',  // Emerald — specialized knowledge
  validation: '#8b5cf6',     // Violet — quality gates
  fix_generation: '#f43f5e', // Rose — code output
};

// Session status → severity tint (rgba for subtle background)
export const SEVERITY_TINTS: Record<string, string> = {
  critical: 'rgba(239, 68, 68, 0.04)',
  error: 'rgba(239, 68, 68, 0.06)',
  running: 'rgba(224, 159, 62, 0.04)',
  healthy: 'transparent',
};
