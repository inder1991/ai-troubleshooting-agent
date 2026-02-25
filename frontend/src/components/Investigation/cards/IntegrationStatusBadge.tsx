import React from 'react';
import type { IntegrationAvailability } from '../../../types';

interface IntegrationStatusBadgeProps {
  integration: IntegrationAvailability;
  name: string;
}

const IntegrationStatusBadge: React.FC<IntegrationStatusBadgeProps> = ({ integration, name }) => {
  if (integration.configured && integration.has_credentials && integration.status === 'connected') {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
        Connected
      </span>
    );
  }

  if (integration.status === 'mock_available') {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
        DEMO
      </span>
    );
  }

  if (integration.configured && integration.status === 'conn_error') {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
        Error
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-slate-500/10 text-slate-500 border border-slate-500/20">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
      Not Configured
    </span>
  );
};

export default IntegrationStatusBadge;
