import React from 'react';

type CausalRole = 'root_cause' | 'cascading_failure' | 'correlated_anomaly';

const roleStyles: Record<CausalRole, { label: string; className: string }> = {
  root_cause: {
    label: 'ROOT CAUSE',
    className: 'bg-red-500/20 text-red-400 border border-red-500/40',
  },
  cascading_failure: {
    label: 'CASCADING SYMPTOM',
    className: 'bg-orange-500/20 text-orange-400 border border-orange-500/40',
  },
  correlated_anomaly: {
    label: 'CORRELATED',
    className: 'bg-slate-500/20 text-slate-400 border border-slate-500/40',
  },
};

interface CausalRoleBadgeProps {
  role: CausalRole;
}

const CausalRoleBadge: React.FC<CausalRoleBadgeProps> = ({ role }) => {
  const style = roleStyles[role];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider ${style.className}`}>
      {style.label}
    </span>
  );
};

export default CausalRoleBadge;
