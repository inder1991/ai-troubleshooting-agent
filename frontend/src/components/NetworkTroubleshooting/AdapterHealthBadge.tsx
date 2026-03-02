import React from 'react';

interface AdapterHealthBadgeProps {
  vendor: string;
  status: string;
}

const STATUS_COLORS: Record<string, string> = {
  connected: '#22c55e',
  unreachable: '#ef4444',
  auth_failed: '#f59e0b',
  not_configured: '#64748b',
};

const AdapterHealthBadge: React.FC<AdapterHealthBadgeProps> = ({ vendor, status }) => {
  const dotColor = STATUS_COLORS[status] || STATUS_COLORS.not_configured;

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-mono text-xs"
      style={{ backgroundColor: '#162a2e', color: '#e2e8f0' }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ backgroundColor: dotColor }}
      />
      {vendor}
    </span>
  );
};

export default AdapterHealthBadge;
