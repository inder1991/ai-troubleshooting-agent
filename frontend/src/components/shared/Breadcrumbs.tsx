import React from 'react';

interface BreadcrumbItem {
  label: string;
  onClick?: () => void;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ items }) => {
  if (items.length <= 1) return null;

  return (
    <nav className="flex items-center gap-1.5 px-8 py-2 border-b border-[#3d3528]/50 bg-[#12110e]/50">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && (
            <span className="material-symbols-outlined text-[12px] text-slate-500">
              chevron_right
            </span>
          )}
          {item.onClick ? (
            <button
              onClick={item.onClick}
              className="text-body-xs font-display text-slate-400 hover:text-[#e09f3e] transition-colors"
            >
              {item.label}
            </button>
          ) : (
            <span className="text-body-xs font-display text-slate-300">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
};
