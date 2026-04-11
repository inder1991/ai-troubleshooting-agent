import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Badge } from '../ui/Badge';

export type NavView = 'home' | 'sessions' | 'cicd' | 'app-diagnostics' | 'cluster-diagnostics'
  | 'network-troubleshooting' | 'pr-review' | 'github-issue-fix'
  | 'network-topology' | 'network-adapters' | 'device-monitoring' | 'ipam' | 'matrix' | 'observatory'
  | 'k8s-clusters' | 'k8s-diagnostics' | 'cluster-registry' | 'cluster-recommendations'
  | 'db-overview' | 'db-connections' | 'db-diagnostics' | 'db-monitoring' | 'db-schema' | 'db-operations'
  | 'integrations' | 'settings' | 'agent-matrix'
  | 'audit-log' | 'mib-browser' | 'cloud-resources' | 'security-resources'
  | 'agent-catalog' | 'workflow-builder' | 'workflow-runs' | 'how-it-works';

type NavChild = { id: NavView; label: string; icon: string; badge?: 'NEW' | 'PREVIEW' | 'BETA' };
type NavLink = { kind: 'link'; id: NavView; label: string; icon: string };
type NavGroup = { kind: 'group'; group: string; icon: string; children: NavChild[] };
type NavItem = NavLink | NavGroup;

interface SidebarNavProps {
  activeView: NavView;
  onNavigate: (view: NavView) => void;
  onNewMission?: () => void;
}

const navItems: NavItem[] = [
  // Zone 1: Entry
  { kind: 'link', id: 'home', label: 'Dashboard', icon: 'space_dashboard' },
  { kind: 'link', id: 'sessions', label: 'Sessions', icon: 'history' },
  { kind: 'link', id: 'cicd', label: 'Delivery', icon: 'rocket_launch' },

  // Zone 2: Diagnostics (merged — all troubleshooting in one group)
  {
    kind: 'group', group: 'Diagnostics', icon: 'troubleshoot',
    children: [
      { id: 'app-diagnostics', label: 'Application', icon: 'bug_report' },
      { id: 'db-diagnostics', label: 'Database', icon: 'database' },
      { id: 'network-troubleshooting', label: 'Network', icon: 'route', badge: 'NEW' },
      { id: 'k8s-diagnostics', label: 'Cluster', icon: 'deployed_code', badge: 'PREVIEW' },
    ],
  },

  // Zone 3: Code
  {
    kind: 'group', group: 'Code', icon: 'code',
    children: [
      { id: 'pr-review', label: 'PR Review', icon: 'rate_review' },
      { id: 'github-issue-fix', label: 'Issue Fixer', icon: 'auto_fix_high' },
    ],
  },

  // Zone 4: Infrastructure
  {
    kind: 'group', group: 'Infrastructure', icon: 'dns',
    children: [
      { id: 'k8s-clusters', label: 'K8s Clusters', icon: 'deployed_code' },
      { id: 'cluster-registry', label: 'Clusters', icon: 'cloud_circle' },
      { id: 'network-topology', label: 'Topology', icon: 'device_hub' },
      { id: 'network-adapters', label: 'Adapters', icon: 'settings_input_component' },
      { id: 'device-monitoring', label: 'Devices', icon: 'router' },
      { id: 'ipam', label: 'IPAM', icon: 'dns' },
    ],
  },

  // Zone 5: Data
  {
    kind: 'group', group: 'Data', icon: 'storage',
    children: [
      { id: 'db-overview', label: 'DB Overview', icon: 'dashboard' },
      { id: 'db-connections', label: 'Connections', icon: 'cable' },
      { id: 'db-monitoring', label: 'Monitoring', icon: 'monitoring' },
      { id: 'db-schema', label: 'Schema', icon: 'account_tree' },
      { id: 'db-operations', label: 'Operations', icon: 'build' },
    ],
  },

  // Zone 6: Monitoring
  {
    kind: 'group', group: 'Monitoring', icon: 'monitoring',
    children: [
      { id: 'observatory', label: 'Observatory', icon: 'monitoring' },
      { id: 'matrix', label: 'Reachability', icon: 'grid_view' },
      { id: 'mib-browser', label: 'MIB Browser', icon: 'manage_search', badge: 'NEW' },
    ],
  },

  // Zone 7: Cloud & Security
  {
    kind: 'group', group: 'Cloud', icon: 'cloud',
    children: [
      { id: 'cloud-resources', label: 'Resources', icon: 'cloud', badge: 'NEW' },
      { id: 'security-resources', label: 'Security', icon: 'security', badge: 'NEW' },
    ],
  },

  // Zone 8: System
  { kind: 'link', id: 'agent-matrix', label: 'Agent Matrix', icon: 'smart_toy' },

  // Zone 9: Platform
  {
    kind: 'group', group: 'Platform', icon: 'hub',
    children: [
      { id: 'workflow-builder', label: 'Workflow Builder', icon: 'account_tree', badge: 'NEW' },
      { id: 'workflow-runs', label: 'Workflow Runs', icon: 'play_circle', badge: 'NEW' },
    ],
  },
  {
    kind: 'group', group: 'Settings', icon: 'settings',
    children: [
      { id: 'integrations', label: 'Integrations', icon: 'hub' },
      { id: 'settings', label: 'Settings', icon: 'settings' },
      { id: 'audit-log', label: 'Audit Log', icon: 'history' },
    ],
  },
];

const iconEl = (name: string, size = 19) => (
  <span
    className="material-symbols-outlined flex-shrink-0 transition-colors duration-200"
    style={{ fontSize: size }}
    aria-hidden="true"
  >
    {name}
  </span>
);

const SidebarNav: React.FC<SidebarNavProps> = ({ activeView, onNavigate, onNewMission }) => {
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);
  const [flyoutY, setFlyoutY] = useState(0);
  const [pinned, setPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar-collapsed') === 'true'; } catch { return false; }
  });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Persist pin state & notify App layout
  useEffect(() => {
    try { localStorage.setItem('sidebar-pinned', String(pinned)); } catch { /* noop */ }
    window.dispatchEvent(new Event('sidebar-pin-change'));
  }, [pinned]);

  // Persist collapsed state & notify App layout
  useEffect(() => {
    try { localStorage.setItem('sidebar-collapsed', String(collapsed)); } catch { /* noop */ }
    window.dispatchEvent(new Event('sidebar-pin-change'));
  }, [collapsed]);

  const activeGroupName = useMemo(() => {
    const item = navItems.find(
      (i) => i.kind === 'group' && i.children.some((c) => c.id === activeView)
    );
    return item?.kind === 'group' ? item.group : null;
  }, [activeView]);

  const displayGroup = hoveredGroup || (pinned ? activeGroupName : null);

  const displayGroupItem = useMemo(() => {
    if (!displayGroup) return null;
    return navItems.find(
      (item) => item.kind === 'group' && item.group === displayGroup
    ) as NavGroup | undefined;
  }, [displayGroup]);

  const handleMouseEnterGroup = (e: React.MouseEvent<HTMLButtonElement>, groupName: string) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);

    // Calculate vertical anchor relative to the outer container
    const containerRect = containerRef.current?.getBoundingClientRect();
    const buttonRect = e.currentTarget.getBoundingClientRect();
    if (containerRect) {
      const offsetY = buttonRect.top - containerRect.top;
      // Clamp so flyout doesn't overflow bottom — estimate flyout height based on group children count
      const estimatedFlyoutHeight = displayGroupItem ? Math.max(200, displayGroupItem.children.length * 40 + 80) : 280;
      const maxY = containerRect.height - estimatedFlyoutHeight;
      setFlyoutY(Math.max(0, Math.min(offsetY, maxY)));
    }

    setHoveredGroup(groupName);  // Instant — flyout has no animation, so no flicker risk
  };

  const handleMouseLeaveNav = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    // Grace period before closing — prevents flyout from closing when moving mouse to it
    if (!pinned) {
      hoverTimerRef.current = setTimeout(() => {
        setHoveredGroup(null);
      }, 200);
    }
  };

  const handlePinToggle = () => {
    setPinned((p) => {
      const next = !p;
      if (!next) setHoveredGroup(null);
      return next;
    });
  };

  // Reset all hover colors on nav items
  const resetHoverStyles = () => {
    if (!containerRef.current) return;
    containerRef.current.querySelectorAll('[data-label]').forEach((el) => {
      (el as HTMLElement).style.color = '';
    });
    containerRef.current.querySelectorAll('[data-icon]').forEach((el) => {
      (el as HTMLElement).style.color = '';
    });
    containerRef.current.querySelectorAll('[data-chevron]').forEach((el) => {
      (el as HTMLElement).style.opacity = '';
    });
  };

  return (
    <div
      ref={containerRef}
      className="flex h-full relative font-sans antialiased select-none"
      onMouseLeave={() => { handleMouseLeaveNav(); resetHoverStyles(); }}
    >
      {/* ─── TIER 1: Persistent Sidebar ─── */}
      <aside
        className={`${collapsed ? 'w-12' : 'w-52'} shrink-0 border-r border-duck-border/40 flex flex-col h-full z-30 relative transition-all duration-200`}
        style={{ background: 'linear-gradient(180deg, #13110d 0%, #161310 100%)' }}
      >
        {/* Brand + Collapse toggle */}
        <div className={`flex items-center ${collapsed ? 'justify-center p-3' : 'justify-between px-4 py-4'} mb-2 flex-shrink-0`}>
          <button
            onClick={() => onNavigate('home')}
            className="flex items-center gap-2.5 group cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent rounded-lg"
            title="Dashboard"
            aria-label="Dashboard"
          >
            <span
              className="material-symbols-outlined text-xl group-hover:scale-110 transition-transform text-duck-accent"
              aria-hidden="true"
            >
              pest_control
            </span>
            {!collapsed && (
              <span className="text-[17px] font-display font-bold tracking-tight text-slate-100">
                DebugDuck
              </span>
            )}
          </button>
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="text-slate-500 hover:text-slate-300 transition-colors p-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              aria-label="Collapse sidebar"
              title="Collapse sidebar"
            >
              <span className="material-symbols-outlined text-[16px]">chevron_left</span>
            </button>
          )}
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              className="text-slate-500 hover:text-slate-300 transition-colors mt-2 p-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              aria-label="Expand sidebar"
              title="Expand sidebar"
            >
              <span className="material-symbols-outlined text-[16px]">chevron_right</span>
            </button>
          )}
        </div>

        {/* Nav Items */}
        <nav className={`flex-1 flex flex-col gap-1 ${collapsed ? 'px-1' : 'px-2'} overflow-y-auto min-h-0 pb-2 custom-scrollbar`}>
          {navItems.map((item) => {
            if (item.kind === 'link') {
              const isActive = activeView === item.id && item.id !== 'home';
              return (
                <button
                  key={item.id}
                  onClick={() => { onNavigate(item.id); setHoveredGroup(null); }}
                  onMouseEnter={(e) => {
                    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
                    if (!pinned) setHoveredGroup(null);
                    resetHoverStyles();
                    if (!isActive) {
                      const label = e.currentTarget.querySelector('[data-label]') as HTMLElement;
                      const icon = e.currentTarget.querySelector('[data-icon]') as HTMLElement;
                      if (label) label.style.color = '#e09f3e';
                      if (icon) icon.style.color = '#e09f3e';
                    }
                  }}
                  title={item.label}
                  aria-label={item.label}
                  className={`
                    relative w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all duration-150 text-left
                    focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent
                    ${isActive
                      ? 'bg-[#13110d] border-l-2 border-l-duck-accent'
                      : 'hover:bg-[#1e1b15]/30 border-l-2 border-l-transparent'
                    }
                  `}
                >
                  <span className={`material-symbols-outlined flex-shrink-0 text-[19px] transition-colors ${isActive ? 'text-[#e09f3e]' : 'text-slate-400'}`} data-icon>{item.icon}</span>
                  {!collapsed && <span className={`text-[12px] font-display font-bold transition-colors ${isActive ? 'text-[#e09f3e]' : 'text-slate-300'}`} data-label>{item.label}</span>}
                </button>
              );
            }

            // Group item
            const hasActiveChild = item.children.some((c) => c.id === activeView);
            const isGroupActive = displayGroup === item.group;
            const isHighlighted = isGroupActive || hasActiveChild;

            return (
              <button
                key={item.group}
                onMouseEnter={(e) => {
                  handleMouseEnterGroup(e, item.group);
                  resetHoverStyles();
                  if (!isHighlighted) {
                    const label = e.currentTarget.querySelector('[data-label]') as HTMLElement;
                    const icon = e.currentTarget.querySelector('[data-icon]') as HTMLElement;
                    const chevron = e.currentTarget.querySelector('[data-chevron]') as HTMLElement;
                    if (label) label.style.color = '#e09f3e';
                    if (icon) icon.style.color = '#e09f3e';
                    if (chevron) chevron.style.opacity = '1';
                  }
                }}
                title={item.group}
                aria-label={item.group}
                aria-expanded={isGroupActive}
                className={`
                  group relative w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all duration-150 text-left
                  focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent
                  ${isGroupActive
                    ? 'bg-[#13110d] rounded-r-none border-l-2 border-l-duck-accent'
                    : hasActiveChild
                      ? 'bg-[#13110d] border-l-2 border-l-duck-accent'
                      : 'hover:bg-[#1e1b15]/30 border-l-2 border-l-transparent'
                  }
                `}
              >
                <span className={`material-symbols-outlined flex-shrink-0 text-[19px] transition-colors ${isHighlighted ? 'text-[#e09f3e]' : 'text-slate-400'}`} data-icon>{item.icon}</span>
                {!collapsed && (
                  <>
                    <span className={`text-[12px] font-display font-bold flex-1 transition-colors ${isHighlighted ? 'text-[#e09f3e]' : 'text-slate-300'}`} data-label>{item.group}</span>
                    <span
                      className="material-symbols-outlined flex-shrink-0 opacity-20 transition-opacity"
                      style={{ fontSize: 15 }}
                      aria-hidden="true"
                      data-chevron
                    >
                      chevron_right
                    </span>
                  </>
                )}
              </button>
            );
          })}
        </nav>

        {/* Bottom: Collapse toggle + Help + User */}
        <div className="flex-shrink-0 border-t border-duck-border/20">
          {!collapsed && (
            <>
              {/* Help & Feedback */}
              <button
                className="w-full flex items-center gap-2.5 px-3 py-2 text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] transition-colors text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
                onClick={() => onNavigate('how-it-works')}
                aria-label="Help and documentation"
              >
                <span className="material-symbols-outlined text-[18px]" aria-hidden="true">help</span>
                <span className="text-[11px] font-display font-bold">Help & Docs</span>
              </button>

              {/* User Profile */}
              <div className="flex items-center gap-2.5 px-3 py-2.5 border-t border-duck-border/10">
                <div className="w-7 h-7 rounded-md bg-duck-accent/20 border border-duck-accent/30 flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined text-[14px] text-duck-accent" aria-hidden="true">person</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-display font-bold text-slate-200 truncate">SRE Admin</p>
                  <p className="text-[9px] text-slate-400 truncate">Acme Corp · Pro Plan</p>
                </div>
              </div>
            </>
          )}

          {collapsed && (
            <div className="flex flex-col items-center gap-2 py-2">
              <button
                onClick={() => onNavigate('how-it-works')}
                className="text-slate-500 hover:text-slate-200 transition-colors"
                aria-label="Help"
                title="Help & Docs"
              >
                <span className="material-symbols-outlined text-[18px]">help</span>
              </button>
              <div className="w-6 h-6 rounded-md bg-duck-accent/20 flex items-center justify-center" title="SRE Admin">
                <span className="material-symbols-outlined text-[12px] text-duck-accent">person</span>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* ─── TIER 2: Flyout Panel — appears/disappears, content swaps without re-animation ─── */}
      {displayGroup && displayGroupItem && (
          <div
            style={{
              position: 'absolute',
              top: flyoutY,
              left: 199,
              transition: 'top 200ms cubic-bezier(0.22, 1, 0.36, 1)',
            }}
            className="w-fit min-w-[215px] max-w-[320px] h-fit max-h-[calc(100vh-16px)] bg-[#13110d] border border-duck-border/15 border-l-0 shadow-2xl z-50 overflow-hidden rounded-r-xl"
          >
            <div className="p-5 flex flex-col">
              {/* Flyout Header */}
              <header className="flex items-center justify-between mb-5 gap-8">
                <h2 className="text-[10px] font-display font-bold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                  {displayGroupItem.group}
                </h2>
                <button
                  onClick={handlePinToggle}
                  title={pinned ? 'Unpin panel' : 'Pin panel open'}
                  aria-label={pinned ? 'Unpin panel' : 'Pin panel open'}
                  className={`p-1 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent ${
                    pinned ? 'text-duck-accent' : 'text-slate-600 hover:text-slate-400'
                  }`}
                  style={{ transition: 'color 150ms cubic-bezier(0.25, 1, 0.5, 1), transform 100ms cubic-bezier(0.25, 1, 0.5, 1)' }}
                  onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.9)'; }}
                  onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
                >
                  <span
                    className="material-symbols-outlined text-[16px]"
                    aria-hidden="true"
                  >
                    {pinned ? 'keep_filled' : 'keep'}
                  </span>
                </button>
              </header>

              {/* Children Links — staggered entrance */}
              <nav className="flex flex-col gap-0.5" role="menu">
                {displayGroupItem.children.map((child) => {
                  const isActive = activeView === child.id;
                  return (
                    <button
                      key={child.id}
                      onClick={() => { onNavigate(child.id); if (!pinned) setHoveredGroup(null); }}
                      role="menuitem"
                      className={`
                        flex items-center justify-between gap-10 px-3 py-1.5 rounded-md text-left whitespace-nowrap
                        focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent
                        ${isActive
                          ? 'bg-duck-accent/10'
                          : 'hover:bg-white/[0.05]'
                        }
                      `}
                      style={{
                        transition: 'background-color 150ms cubic-bezier(0.25, 1, 0.5, 1), transform 150ms cubic-bezier(0.25, 1, 0.5, 1)',
                      }}
                      onMouseEnter={(e) => {
                        const label = e.currentTarget.querySelector('[data-label]') as HTMLElement;
                        const icon = e.currentTarget.querySelector('[data-icon]') as HTMLElement;
                        if (label) label.style.color = '#e09f3e';
                        if (icon) icon.style.opacity = '1';
                        if (!isActive) e.currentTarget.style.transform = 'translateX(3px)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateX(0)';
                        if (isActive) return;
                        const label = e.currentTarget.querySelector('[data-label]') as HTMLElement;
                        const icon = e.currentTarget.querySelector('[data-icon]') as HTMLElement;
                        if (label) label.style.color = '';
                        if (icon) icon.style.opacity = '';
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <span className={`transition-opacity ${isActive ? 'opacity-100' : 'opacity-60'}`} data-icon>{iconEl(child.icon, 18)}</span>
                        <span className={`text-xs font-medium transition-colors ${isActive ? 'text-[#e09f3e]' : 'text-slate-400'}`} data-label>{child.label}</span>
                      </div>
                      {child.badge && <Badge type={child.badge} />}
                    </button>
                  );
                })}
              </nav>
            </div>
          </div>
      )}
    </div>
  );
};

export default SidebarNav;
