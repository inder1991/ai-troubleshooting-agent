import React, { useState, useEffect, useRef } from 'react';

export type NavView = 'home' | 'sessions' | 'app-diagnostics' | 'cluster-diagnostics'
  | 'network-troubleshooting' | 'pr-review' | 'github-issue-fix'
  | 'network-topology' | 'network-adapters' | 'device-monitoring' | 'ipam' | 'matrix' | 'observatory'
  | 'k8s-clusters' | 'k8s-diagnostics'
  | 'db-overview' | 'db-connections' | 'db-diagnostics' | 'db-monitoring' | 'db-schema' | 'db-operations'
  | 'integrations' | 'settings' | 'agents';

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
      { id: 'app-diagnostics', label: 'Application', icon: 'bug_report' },
      { id: 'k8s-diagnostics', label: 'Cluster', icon: 'health_and_safety' },
      { id: 'db-diagnostics', label: 'Database', icon: 'storage' },
      { id: 'network-troubleshooting', label: 'Network', icon: 'route' },
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
    kind: 'group', group: 'Kubernetes', icon: 'cloud',
    children: [
      { id: 'k8s-clusters', label: 'Clusters', icon: 'dns' },
      { id: 'k8s-diagnostics', label: 'Diagnostics', icon: 'troubleshoot' },
    ],
  },
  {
    kind: 'group', group: 'Database', icon: 'storage',
    children: [
      { id: 'db-overview', label: 'Overview', icon: 'dashboard' },
      { id: 'db-connections', label: 'Connections', icon: 'cable' },
      { id: 'db-diagnostics', label: 'Diagnostics', icon: 'troubleshoot' },
      { id: 'db-monitoring', label: 'Monitoring', icon: 'monitoring' },
      { id: 'db-schema', label: 'Schema', icon: 'account_tree' },
      { id: 'db-operations', label: 'Operations', icon: 'build' },
    ],
  },
  {
    kind: 'group', group: 'Networking', icon: 'lan',
    children: [
      { id: 'network-topology', label: 'Topology', icon: 'device_hub' },
      { id: 'network-adapters', label: 'Adapters', icon: 'settings_input_component' },
      { id: 'device-monitoring', label: 'Device Monitoring', icon: 'router' },
      { id: 'ipam', label: 'IPAM', icon: 'dns' },
      { id: 'observatory', label: 'Observatory', icon: 'monitoring' },
      { id: 'matrix', label: 'Matrix', icon: 'grid_view' },
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
  const activeRef = useRef<HTMLButtonElement>(null);

  // Auto-expand group containing the active view
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

  // Scroll active item into view on mount/change
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [activeView]);

  const toggleGroup = (group: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const iconEl = (name: string, size = 20) => (
    <span
      className="material-symbols-outlined flex-shrink-0"
      style={{ fontFamily: 'Material Symbols Outlined', fontSize: size }}
    >
      {name}
    </span>
  );

  const renderLink = (id: NavView, label: string, icon: string, indented = false) => {
    const isActive = activeView === id;
    return (
      <button
        key={id}
        ref={isActive ? activeRef : undefined}
        onClick={() => onNavigate(id)}
        title={collapsed ? label : undefined}
        className={`
          relative flex items-center gap-2.5 rounded-md transition-all duration-150
          ${collapsed ? 'justify-center px-0 py-2' : 'px-3 py-[7px]'}
          ${isActive
            ? 'text-cyan-300 bg-cyan-500/10'
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
          }
        `}
        style={!collapsed && indented ? { paddingLeft: '2.5rem' } : {}}
      >
        {/* Active left accent bar */}
        {isActive && !collapsed && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-cyan-400" />
        )}
        {iconEl(icon, indented ? 18 : 20)}
        {!collapsed && (
          <span className={`text-[13px] leading-tight ${isActive ? 'font-semibold' : 'font-medium'}`}>
            {label}
          </span>
        )}
      </button>
    );
  };

  return (
    <aside
      className={`${collapsed ? 'w-[60px]' : 'w-60'} flex-shrink-0 border-r border-[#1a3a40] flex flex-col h-full transition-all duration-200`}
      style={{ backgroundColor: '#0c1a1e' }}
    >
      {/* ─── Brand Header (fixed) ─── */}
      <div className={`${collapsed ? 'px-2 py-4' : 'px-5 py-5'} flex items-center ${collapsed ? 'justify-center' : 'justify-between'} flex-shrink-0`}>
        <div className={`flex items-center ${collapsed ? '' : 'gap-3'}`}>
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: 'rgba(7,182,213,0.15)', border: '1px solid rgba(7,182,213,0.25)' }}
          >
            <span className="material-symbols-outlined text-xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>pest_control</span>
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <h1 className="text-white text-[15px] font-bold leading-none tracking-tight">DebugDuck</h1>
              <p className="text-[9px] font-bold uppercase tracking-[0.15em] mt-0.5" style={{ color: '#07b6d5' }}>Command Center</p>
            </div>
          )}
        </div>
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="text-slate-500 hover:text-white transition-colors p-0.5 rounded"
            title="Collapse sidebar"
          >
            {iconEl('chevron_left', 18)}
          </button>
        )}
      </div>

      {/* Expand toggle when collapsed */}
      {collapsed && (
        <div className="px-2 flex justify-center mb-2">
          <button
            onClick={() => setCollapsed(false)}
            className="text-slate-500 hover:text-white transition-colors p-0.5 rounded"
            title="Expand sidebar"
          >
            {iconEl('chevron_right', 18)}
          </button>
        </div>
      )}

      {/* ─── Scrollable Nav ─── */}
      <nav
        className={`flex-1 flex flex-col gap-0.5 ${collapsed ? 'px-1.5' : 'px-2.5'} overflow-y-auto min-h-0 pb-2 sidebar-scroll`}
      >
        {navItems.map((item, idx) => {
          if (item.kind === 'link') {
            if (collapsed) {
              return (
                <div key={item.id}>
                  {idx > 0 && <div className="my-1.5 mx-1 border-t border-[#1a3a40]" />}
                  {renderLink(item.id, item.label, item.icon)}
                </div>
              );
            }
            return (
              <div key={item.id}>
                {idx > 0 && <div className="mt-3 mb-1" />}
                {renderLink(item.id, item.label, item.icon)}
              </div>
            );
          }

          if (collapsed) {
            return (
              <div key={item.group}>
                {idx > 0 && <div className="my-1.5 mx-1 border-t border-[#1a3a40]" />}
                {item.children.map((child) => renderLink(child.id, child.label, child.icon))}
              </div>
            );
          }

          // Expanded: group with header + children
          const isExpanded = expandedGroups.has(item.group);
          const hasActiveChild = item.children.some((c) => c.id === activeView);

          return (
            <div key={item.group}>
              {idx > 0 && <div className="mt-3 mb-0.5" />}

              {/* Group header */}
              <button
                onClick={() => toggleGroup(item.group)}
                className={`
                  w-full flex items-center gap-2.5 px-3 py-[7px] rounded-md transition-all duration-150
                  ${hasActiveChild
                    ? 'text-cyan-400'
                    : 'text-slate-500 hover:text-slate-300'
                  }
                `}
              >
                {iconEl(item.icon, 20)}
                <span className={`text-[13px] flex-1 text-left ${hasActiveChild ? 'font-semibold text-cyan-400' : 'font-medium'}`}>
                  {item.group}
                </span>
                <span
                  className="material-symbols-outlined text-[14px] opacity-50 transition-transform duration-200"
                  style={{ fontFamily: 'Material Symbols Outlined', transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
                >
                  expand_more
                </span>
              </button>

              {/* Children with animated expand */}
              <div
                className="overflow-hidden transition-all duration-200 ease-out"
                style={{
                  maxHeight: isExpanded ? `${item.children.length * 36 + 4}px` : '0px',
                  opacity: isExpanded ? 1 : 0,
                }}
              >
                <div className="flex flex-col gap-px mt-0.5 ml-4 pl-2.5 border-l border-[#1a3a40]">
                  {item.children.map((child) => renderLink(child.id, child.label, child.icon, true))}
                </div>
              </div>
            </div>
          );
        })}
      </nav>

      {/* ─── Bottom Action (fixed) ─── */}
      <div className={`${collapsed ? 'px-1.5' : 'px-3'} py-4 flex-shrink-0 border-t border-[#1a3a40]`}>
        <button
          onClick={onNewMission}
          title={collapsed ? 'New Mission' : undefined}
          className="w-full flex items-center justify-center gap-2 font-bold py-2.5 rounded-lg transition-all group hover:shadow-lg"
          style={{ backgroundColor: '#07b6d5', color: '#0c1a1e', boxShadow: '0 2px 12px rgba(7,182,213,0.15)' }}
        >
          <span className="material-symbols-outlined text-[20px] group-hover:rotate-180 transition-transform duration-500" style={{ fontFamily: 'Material Symbols Outlined' }}>add_circle</span>
          {!collapsed && <span className="text-sm">New Mission</span>}
        </button>
      </div>
    </aside>
  );
};

export default SidebarNav;
