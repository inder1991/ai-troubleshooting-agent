import React, { useState, useEffect } from 'react';

export type NavView = 'home' | 'sessions' | 'app-diagnostics' | 'cluster-diagnostics'
  | 'network-troubleshooting' | 'pr-review' | 'github-issue-fix'
  | 'network-topology' | 'network-adapters' | 'ipam' | 'matrix' | 'observatory'
  | 'database' | 'integrations' | 'settings' | 'agents';

type NavLink = { kind: 'link'; id: NavView; label: string; icon: string };
type NavGroup = { kind: 'group'; group: string; icon: string; children: { id: NavView; label: string; icon: string }[] };
type NavItem = NavLink | NavGroup;

interface SidebarNavProps {
  activeView: NavView;
  onNavigate: (view: NavView) => void;
  onNewMission?: () => void;
}

const navItems: NavItem[] = [
  { kind: 'link', id: 'home', label: 'Dashboard', icon: 'space_dashboard' },
  {
    kind: 'group', group: 'Diagnostics', icon: 'troubleshoot',
    children: [
      { id: 'app-diagnostics', label: 'App Diagnostics', icon: 'bug_report' },
      { id: 'cluster-diagnostics', label: 'Cluster Diagnostics', icon: 'health_and_safety' },
      { id: 'network-troubleshooting', label: 'Network Path', icon: 'route' },
      { id: 'sessions', label: 'Sessions', icon: 'history' },
    ],
  },
  {
    kind: 'group', group: 'Code', icon: 'code',
    children: [
      { id: 'pr-review', label: 'PR Review', icon: 'rate_review' },
      { id: 'github-issue-fix', label: 'Issue Fixer', icon: 'auto_fix_high' },
    ],
  },
  {
    kind: 'group', group: 'Infrastructure', icon: 'lan',
    children: [
      { id: 'network-topology', label: 'Topology', icon: 'device_hub' },
      { id: 'network-adapters', label: 'Adapters', icon: 'settings_input_component' },
      { id: 'ipam', label: 'IPAM', icon: 'dns' },
      { id: 'observatory', label: 'Observatory', icon: 'monitoring' },
      { id: 'matrix', label: 'Matrix', icon: 'grid_view' },
      { id: 'database', label: 'Databases', icon: 'storage' },
    ],
  },
  {
    kind: 'group', group: 'Configuration', icon: 'build',
    children: [
      { id: 'integrations', label: 'Integrations', icon: 'hub' },
      { id: 'settings', label: 'Settings', icon: 'settings' },
      { id: 'agents', label: 'Agent Matrix', icon: 'smart_toy' },
    ],
  },
];

const SidebarNav: React.FC<SidebarNavProps> = ({ activeView, onNavigate, onNewMission }) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState(false);

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
        title={collapsed ? label : undefined}
        className={`flex items-center ${collapsed ? 'justify-center' : ''} gap-3 ${collapsed ? 'px-0 py-2.5' : 'px-3 py-2.5'} rounded-lg transition-colors border ${
          isActive
            ? 'text-[#07b6d5]'
            : 'text-slate-400 hover:text-white border-transparent'
        }`}
        style={{
          ...(isActive ? {
            backgroundColor: 'rgba(7,182,213,0.1)',
            borderColor: 'rgba(7,182,213,0.2)',
          } : {}),
          ...(!collapsed && indented ? { paddingLeft: '2.25rem' } : {}),
        }}
      >
        <span className="material-symbols-outlined text-[20px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
        {!collapsed && (
          <span className={`text-sm ${isActive ? 'font-semibold tracking-wide' : 'font-medium'}`}>{label}</span>
        )}
      </button>
    );
  };

  return (
    <aside
      className={`${collapsed ? 'w-16' : 'w-64'} flex-shrink-0 border-r border-[#224349] flex flex-col justify-between py-6 transition-all duration-200`}
      style={{ backgroundColor: '#0f2023' }}
    >
      <div className="flex flex-col gap-8">
        {/* Brand Logo + Collapse Toggle */}
        <div className={`${collapsed ? 'px-2' : 'px-6'} flex items-center ${collapsed ? 'justify-center' : 'justify-between'}`}>
          <div className={`flex items-center ${collapsed ? '' : 'gap-3'}`}>
            <div className="w-10 h-10 rounded-lg flex items-center justify-center border flex-shrink-0" style={{ backgroundColor: 'rgba(7,182,213,0.2)', borderColor: 'rgba(7,182,213,0.3)' }}>
              <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>pest_control</span>
            </div>
            {!collapsed && (
              <div className="flex flex-col">
                <h1 className="text-white text-lg font-bold leading-none tracking-tight">DebugDuck</h1>
                <p className="text-[10px] font-bold uppercase tracking-widest mt-1" style={{ color: '#07b6d5' }}>Command Center</p>
              </div>
            )}
          </div>
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="text-slate-500 hover:text-white transition-colors p-1 rounded"
              title="Collapse sidebar"
            >
              <span className="material-symbols-outlined text-[18px]" style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_left</span>
            </button>
          )}
        </div>

        {/* Expand toggle when collapsed */}
        {collapsed && (
          <div className="px-2 flex justify-center">
            <button
              onClick={() => setCollapsed(false)}
              className="text-slate-500 hover:text-white transition-colors p-1 rounded"
              title="Expand sidebar"
            >
              <span className="material-symbols-outlined text-[18px]" style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
            </button>
          </div>
        )}

        {/* Navigation Links */}
        <nav className={`flex flex-col gap-1 ${collapsed ? 'px-2' : 'px-3'}`}>
          {navItems.map((item, idx) => {
            if (item.kind === 'link') {
              // Standalone link (e.g., Dashboard)
              if (collapsed) {
                return (
                  <div key={item.id}>
                    {idx > 0 && <div className="my-2 mx-1 border-t border-[#224349]" />}
                    {renderLink(item.id, item.label, item.icon)}
                  </div>
                );
              }
              return (
                <div key={item.id}>
                  {idx > 0 && <div className="my-1" />}
                  {renderLink(item.id, item.label, item.icon)}
                </div>
              );
            }

            if (collapsed) {
              // Collapsed: thin divider between groups, flat icon list
              return (
                <div key={item.group}>
                  {idx > 0 && (
                    <div className="my-2 mx-1 border-t border-[#224349]" />
                  )}
                  {item.children.map((child) => renderLink(child.id, child.label, child.icon))}
                </div>
              );
            }

            // Expanded: group headers with expand/collapse
            const isExpanded = expandedGroups.has(item.group);
            const hasActiveChild = item.children.some((c) => c.id === activeView);

            return (
              <div key={item.group}>
                {idx > 0 && <div className="my-1" />}
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
      <div className={collapsed ? 'px-2' : 'px-4'}>
        <button
          onClick={onNewMission}
          title={collapsed ? 'New Mission' : undefined}
          className={`w-full flex items-center justify-center gap-2 font-bold py-2.5 rounded-lg transition-all group`}
          style={{ backgroundColor: '#07b6d5', color: '#0f2023', boxShadow: '0 4px 14px rgba(7,182,213,0.1)' }}
        >
          <span className="material-symbols-outlined text-[20px] group-hover:rotate-180 transition-transform duration-500" style={{ fontFamily: 'Material Symbols Outlined' }}>add_circle</span>
          {!collapsed && <span className="text-sm">New Mission</span>}
        </button>
      </div>
    </aside>
  );
};

export default SidebarNav;
