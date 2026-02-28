import React from 'react';

interface ResourceVelocityProps {
  label?: string;
}

const ResourceVelocity: React.FC<ResourceVelocityProps> = ({ label = 'Resource Velocity' }) => {
  return (
    <div className="h-40 bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-2">{label}</h3>
      <svg className="w-full h-full" viewBox="0 0 200 80" preserveAspectRatio="none">
        <path d="M0 40 L200 40" stroke="#1f3b42" strokeDasharray="2" strokeWidth="1" />
        <text x="5" y="35" fill="#1f3b42" fontFamily="monospace" fontSize="6">REQUEST_LIMIT</text>
        <path
          d="M0 70 Q 20 65, 40 68 T 80 50 T 120 20 T 160 30 T 200 15 L 200 80 L 0 80 Z"
          fill="rgba(19, 182, 236, 0.1)"
        />
        <path
          d="M0 70 Q 20 65, 40 68 T 80 50 T 120 20 T 160 30 T 200 15"
          fill="none"
          stroke="#13b6ec"
          strokeWidth="1.5"
        />
        <path
          d="M85 40 Q 120 20, 160 30 T 200 15 L 200 40 Z"
          className="pressure-zone-fill"
        />
      </svg>
    </div>
  );
};

export default ResourceVelocity;
