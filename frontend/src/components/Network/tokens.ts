/** NDM Design Tokens — centralized color and spacing constants */

export const colors = {
  primary: '#07b6d5',
  primaryBg: 'rgba(7,182,213,0.04)',
  primaryBorder: 'rgba(7,182,213,0.12)',
  primaryHover: 'rgba(7,182,213,0.3)',
  primaryLight: 'rgba(7,182,213,0.1)',
  primaryMedium: 'rgba(7,182,213,0.2)',

  success: '#22c55e',
  successBg: 'rgba(34,197,94,0.12)',
  warning: '#f59e0b',
  warningBg: 'rgba(245,158,11,0.12)',
  error: '#ef4444',
  errorBg: 'rgba(239,68,68,0.06)',
  errorBorder: 'rgba(239,68,68,0.2)',

  text: '#e2e8f0',
  textMuted: '#94a3b8',
  textDim: '#64748b',
  textDisabled: '#475569',

  bgCard: 'rgba(7,182,213,0.04)',
  bgDark: 'rgba(15,32,35,0.5)',
  borderSubtle: 'rgba(148,163,184,0.06)',
  borderLight: 'rgba(148,163,184,0.12)',
  borderMuted: 'rgba(148,163,184,0.2)',
} as const;

export const status: Record<string, string> = {
  up: colors.success,
  down: colors.error,
  unreachable: colors.warning,
  new: colors.textMuted,
  healthy: colors.success,
  degraded: colors.warning,
  critical: colors.error,
};

export const severity: Record<string, string> = {
  emergency: colors.error,
  alert: colors.error,
  critical: colors.error,
  error: '#f97316',
  warning: colors.warning,
  notice: colors.primary,
  info: colors.textMuted,
  debug: colors.textDim,
};

export const cardStyle: React.CSSProperties = {
  background: colors.bgCard,
  border: `1px solid ${colors.primaryBorder}`,
  borderRadius: 10,
  padding: 20,
};

export const tooltipStyle = {
  contentStyle: {
    background: '#0f2023',
    border: '1px solid rgba(7,182,213,0.2)',
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: colors.text },
  itemStyle: { color: colors.textMuted },
};

import type React from 'react';
