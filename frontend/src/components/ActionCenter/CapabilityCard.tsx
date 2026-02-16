import React from 'react';
import type { LucideIcon } from 'lucide-react';
import type { CapabilityType } from '../../types';

interface CapabilityCardProps {
  capability: CapabilityType;
  title: string;
  description: string;
  icon: LucideIcon;
  color: string;
  onSelect: (capability: CapabilityType) => void;
}

const CapabilityCard: React.FC<CapabilityCardProps> = ({
  capability,
  title,
  description,
  icon: Icon,
  color,
  onSelect,
}) => {
  return (
    <button
      onClick={() => onSelect(capability)}
      className="group relative bg-[#1e2f33]/50 border border-[#224349] rounded-xl p-6 text-left transition-all duration-200 hover:border-opacity-60 hover:shadow-lg hover:shadow-black/20 hover:-translate-y-0.5"
      style={{ '--card-accent': color } as React.CSSProperties}
    >
      {/* Accent glow */}
      <div
        className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ background: `radial-gradient(ellipse at top left, ${color}08, transparent 70%)` }}
      />

      <div className="relative">
        {/* Icon */}
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center mb-4"
          style={{ backgroundColor: `${color}15`, border: `1px solid ${color}30` }}
        >
          <Icon className="w-5 h-5" style={{ color }} />
        </div>

        {/* Title */}
        <h3 className="text-white font-semibold text-sm mb-2">{title}</h3>

        {/* Description */}
        <p className="text-gray-400 text-xs leading-relaxed">{description}</p>

        {/* Launch indicator */}
        <div className="mt-4 flex items-center gap-1.5 text-xs font-medium" style={{ color }}>
          <span>Launch</span>
          <svg className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    </button>
  );
};

export default CapabilityCard;
