import React, { useState, useEffect } from 'react';

export type NavView = 'home' | 'sessions' | 'integrations' | 'settings' | 'agents' | 'network-topology' | 'ipam' | 'matrix';

type NavLink = { kind: 'link'; id: NavView; label: string; icon: string };
type NavGroup = { kind: 'group'; group: string; icon: string; children: { id: NavView; label: string; icon: string }[] };
type NavItem = NavLink | NavGroup;

interface SidebarNavProps {
  activeView: NavView;
  onNavigate: (view: NavView) => void;
  onNewMission?: () => void;
}

const navItems: NavItem[] = [
  { kind: 'link', id: 'home', label: 'Dashboard', icon: 'dashboard' },
  { kind: 'link', id: 'sessions', label: 'Sessions', icon: 'history' },
  {
    kind: 'group',
    group: 'Network',
    icon: 'lan',
    children: [
      { id: 'network-topology', label: 'Topology', icon: 'device_hub' },
      { id: 'ipam', label: 'IPAM', icon: 'dns' },
      { id: 'matrix', label: 'Matrix', icon: 'grid_view' },
    ],
  },
  { kind: 'link', id: 'integrations', label: 'Integrations', icon: 'hub' },
  { kind: 'link', id: 'settings', label: 'Settings', icon: 'settings' },
  { kind: 'link', id: 'agents' as NavView, label: 'Agent Matrix', icon: 'smart_toy' },
];

const SidebarNav: React.FC<SidebarNavProps> = ({ activeView, onNavigate, onNewMission }) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // Auto-expand group if active view is one of its children
  useEffect(() => {
    for (const item of navItems) {
      if (item.kind === 'group' && item.children.some((c) => c.id === activeView)) {
        setExpandedGroups((prev) => {
          if (prev.has(item.group)) return prev;
          const next = new Set(prev);
          next.add(item.group);
          return next;
        });
      }
    }
  }, [activeView]);

  const toggleGroup = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const renderLink = (id: NavView, label: string, icon: string, indented = false) => {
    const isActive = activeView === id;
    return (
      <button
        key={id}
        onClick={() => onNavigate(id)}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors border ${
          isActive
            ? 'text-[#07b6d5]'
            : 'text-slate-400 hover:text-white border-transparent'
        }`}
        style={{
          ...(isActive ? {
            backgroundColor: 'rgba(7,182,213,0.1)',
            borderColor: 'rgba(7,182,213,0.2)',
          } : {}),
          ...(indented ? { paddingLeft: '2.25rem' } : {}),
        }}
      >
        <span className="material-symbols-outlined text-[20px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
        <span className={`text-sm ${isActive ? 'font-semibold tracking-wide' : 'font-medium'}`}>{label}</span>
      </button>
    );
  };

  return (
    <aside className="w-64 flex-shrink-0 border-r border-[#224349] flex flex-col justify-between py-6" style={{ backgroundColor: '#0f2023' }}>
      <div className="flex flex-col gap-8">
        {/* Brand Logo */}
        <div className="px-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center border" style={{ backgroundColor: 'rgba(7,182,213,0.2)', borderColor: 'rgba(7,182,213,0.3)' }}>
            <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>pest_control</span>
          </div>
          <div className="flex flex-col">
            <h1 className="text-white text-lg font-bold leading-none tracking-tight">DebugDuck</h1>
            <p className="text-[10px] font-bold uppercase tracking-widest mt-1" style={{ color: '#07b6d5' }}>Command Center</p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex flex-col gap-1 px-3">
          {navItems.map((item) => {
            if (item.kind === 'link') {
              return renderLink(item.id, item.label, item.icon);
            }

            // Group
            const isExpanded = expandedGroups.has(item.group);
            const hasActiveChild = item.children.some((c) => c.id === activeView);

            return (
              <div key={item.group}>
                <button
                  onClick={() => toggleGroup(item.group)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors border ${
                    hasActiveChild
                      ? 'text-[#07b6d5]'
                      : 'text-slate-400 hover:text-white border-transparent'
                  }`}
                  style={hasActiveChild ? {
                    backgroundColor: 'rgba(7,182,213,0.05)',
                    borderColor: 'rgba(7,182,213,0.15)',
                  } : {}}
                >
                  <span className="material-symbols-outlined text-[20px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{item.icon}</span>
                  <span className={`text-sm flex-1 text-left ${hasActiveChild ? 'font-semibold tracking-wide' : 'font-medium'}`}>{item.group}</span>
                  <span
                    className="material-symbols-outlined text-[16px] transition-transform duration-200"
                    style={{ fontFamily: 'Material Symbols Outlined', transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
                  >
                    expand_more
                  </span>
                </button>
                {isExpanded && (
                  <div className="flex flex-col gap-0.5 mt-0.5">
                    {item.children.map((child) => renderLink(child.id, child.label, child.icon, true))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      {/* Sidebar Bottom Action */}
      <div className="px-4">
        <button
          onClick={onNewMission}
          className="w-full flex items-center justify-center gap-2 font-bold py-2.5 rounded-lg transition-all group"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023', boxShadow: '0 4px 14px rgba(7,182,213,0.1)' }}
        >
          <span className="material-symbols-outlined text-[20px] group-hover:rotate-180 transition-transform duration-500" style={{ fontFamily: 'Material Symbols Outlined' }}>add_circle</span>
          <span className="text-sm">New Mission</span>
        </button>
      </div>
    </aside>
  );
};

export default SidebarNav;
