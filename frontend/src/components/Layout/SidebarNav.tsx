import React, { useState, useMemo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Badge } from '../ui/Badge';

export type NavView = 'home' | 'sessions' | 'app-diagnostics' | 'cluster-diagnostics'
  | 'network-troubleshooting' | 'pr-review' | 'github-issue-fix'
  | 'network-topology' | 'network-adapters' | 'device-monitoring' | 'ipam' | 'matrix' | 'observatory'
  | 'k8s-clusters' | 'k8s-diagnostics'
  | 'db-overview' | 'db-connections' | 'db-diagnostics' | 'db-monitoring' | 'db-schema' | 'db-operations'
  | 'integrations' | 'settings' | 'agents';

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
  { kind: 'link', id: 'home', label: 'Dashboard', icon: 'space_dashboard' },
  {
    kind: 'group', group: 'Diagnostics', icon: 'troubleshoot',
    children: [
      { id: 'app-diagnostics', label: 'Application', icon: 'bug_report' },
      { id: 'k8s-diagnostics', label: 'Cluster', icon: 'health_and_safety', badge: 'PREVIEW' },
      { id: 'db-diagnostics', label: 'Database', icon: 'storage' },
      { id: 'network-troubleshooting', label: 'Network', icon: 'route', badge: 'NEW' },
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

const iconEl = (name: string, size = 19) => (
  <span
    className="material-symbols-outlined flex-shrink-0 transition-colors duration-200"
    style={{ fontSize: size }}
    aria-hidden="true"
  >
    {name}
  </span>
);

const flyoutSpring = { type: 'spring' as const, stiffness: 500, damping: 42 };

const SidebarNav: React.FC<SidebarNavProps> = ({ activeView, onNavigate, onNewMission }) => {
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);
  const [flyoutY, setFlyoutY] = useState(0);
  const [pinned, setPinned] = useState(() => {
    try { return localStorage.getItem('sidebar-pinned') === 'true'; } catch { return false; }
  });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Persist pin state & notify App layout
  useEffect(() => {
    try { localStorage.setItem('sidebar-pinned', String(pinned)); } catch { /* noop */ }
    window.dispatchEvent(new Event('sidebar-pin-change'));
  }, [pinned]);

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
      // Clamp so flyout doesn't overflow bottom (estimate ~280px max flyout height)
      const maxY = containerRect.height - 280;
      setFlyoutY(Math.max(0, Math.min(offsetY, maxY)));
    }

    hoverTimerRef.current = setTimeout(() => {
      setHoveredGroup(groupName);
    }, 60);
  };

  const handleMouseLeaveNav = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    if (!pinned) setHoveredGroup(null);
  };

  const handlePinToggle = () => {
    setPinned((p) => {
      const next = !p;
      if (!next) setHoveredGroup(null);
      return next;
    });
  };

  return (
    <div
      ref={containerRef}
      className="flex h-full relative font-sans antialiased select-none"
      onMouseLeave={handleMouseLeaveNav}
    >
      {/* ─── TIER 1: Persistent Sidebar ─── */}
      <aside className="w-52 shrink-0 bg-duck-sidebar border-r border-white/5 flex flex-col h-full z-30 relative shadow-2xl">
        {/* Brand */}
        <div className="flex items-center gap-2.5 p-5 mb-4 flex-shrink-0">
          <button
            onClick={() => onNavigate('home')}
            className="flex items-center gap-2.5 group cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 rounded-lg"
            title="Dashboard"
            aria-label="Dashboard"
          >
            <span
              className="material-symbols-outlined text-xl group-hover:scale-110 transition-transform text-duck-accent"
              aria-hidden="true"
            >
              pest_control
            </span>
            <span className="text-[17px] font-[900] uppercase tracking-tighter text-slate-100">
              DebugDuck
            </span>
          </button>
        </div>

        {/* Nav Items */}
        <nav className="flex-1 flex flex-col gap-0.5 px-2 overflow-y-auto min-h-0 pb-2 custom-scrollbar">
          {navItems.map((item) => {
            if (item.kind === 'link') {
              const isActive = activeView === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  title={item.label}
                  aria-label={item.label}
                  className={`
                    relative w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all duration-150 text-left
                    focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400
                    ${isActive
                      ? 'text-cyan-400 bg-white/[0.08]'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                    }
                  `}
                >
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-cyan-500 rounded-r-full shadow-[0_0_10px_rgba(6,182,212,0.4)]" />
                  )}
                  <span className={`material-symbols-outlined flex-shrink-0 text-[19px] ${isActive ? 'text-cyan-400' : 'text-slate-500'}`}>{item.icon}</span>
                  <span className="text-[12px] font-semibold tracking-tight">{item.label}</span>
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
                onMouseEnter={(e) => handleMouseEnterGroup(e, item.group)}
                title={item.group}
                aria-label={item.group}
                aria-expanded={isGroupActive}
                className={`
                  group relative w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all duration-150 text-left
                  focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400
                  ${isHighlighted
                    ? 'text-cyan-400 bg-white/[0.08]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }
                `}
              >
                {isHighlighted && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-cyan-500 rounded-r-full shadow-[0_0_10px_rgba(6,182,212,0.4)]" />
                )}
                <span className={`material-symbols-outlined flex-shrink-0 text-[19px] ${isHighlighted ? 'text-cyan-400' : 'text-slate-500'}`}>{item.icon}</span>
                <span className="text-[12px] font-semibold tracking-tight flex-1">{item.group}</span>
                <span
                  className="material-symbols-outlined flex-shrink-0 opacity-20 group-hover:opacity-100 transition-opacity"
                  style={{ fontSize: 15 }}
                  aria-hidden="true"
                >
                  chevron_right
                </span>
              </button>
            );
          })}
        </nav>

        {/* Bottom: New Mission */}
        <div className="px-3 py-4 flex-shrink-0 border-t border-white/5">
          <button
            onClick={onNewMission}
            title="New Mission"
            aria-label="Start New Mission"
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg transition-all hover:shadow-lg group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent bg-duck-accent text-duck-bg shadow-[0_2px_12px_rgba(7,182,213,0.15)]"
          >
            <span
              className="material-symbols-outlined text-[20px] group-hover:rotate-180 transition-transform duration-500"
              aria-hidden="true"
            >
              add_circle
            </span>
            <span className="text-xs font-bold uppercase tracking-wide">New Mission</span>
          </button>
        </div>
      </aside>

      {/* ─── TIER 2: Elastic Hover Flyout ─── */}
      <AnimatePresence>
        {displayGroup && displayGroupItem && (
          <motion.div
            key={displayGroup}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0, y: flyoutY }}
            exit={{ opacity: 0, x: -12 }}
            transition={flyoutSpring}
            style={{ position: 'absolute', top: 0, left: 208 }}
            className="w-fit min-w-[215px] max-w-[320px] h-fit max-h-[calc(100vh-16px)] bg-duck-flyout/95 backdrop-blur-xl border border-white/5 shadow-[0_25px_50px_-12px_rgba(0,0,0,0.8)] z-20 overflow-hidden rounded-xl"
          >
            <div className="p-5 flex flex-col">
              {/* Flyout Header */}
              <header className="flex items-center justify-between mb-5 gap-8">
                <h2 className="text-[10px] font-[900] uppercase tracking-[0.25em] text-slate-500 whitespace-nowrap">
                  {displayGroupItem.group}
                </h2>
                <button
                  onClick={handlePinToggle}
                  title={pinned ? 'Unpin panel' : 'Pin panel open'}
                  aria-label={pinned ? 'Unpin panel' : 'Pin panel open'}
                  className={`p-1 rounded transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                    pinned ? 'text-cyan-400' : 'text-slate-600 hover:text-slate-400'
                  }`}
                >
                  <span
                    className="material-symbols-outlined text-[16px]"
                    aria-hidden="true"
                  >
                    {pinned ? 'keep_filled' : 'keep'}
                  </span>
                </button>
              </header>

              {/* Children Links */}
              <nav className="flex flex-col gap-0.5" role="menu">
                {displayGroupItem.children.map((child) => {
                  const isActive = activeView === child.id;
                  return (
                    <button
                      key={child.id}
                      onClick={() => onNavigate(child.id)}
                      role="menuitem"
                      className={`
                        flex items-center justify-between gap-10 px-3 py-1.5 rounded-md transition-all duration-150 text-left whitespace-nowrap
                        focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400
                        ${isActive
                          ? 'text-cyan-400 bg-cyan-400/10'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.05]'
                        }
                      `}
                    >
                      <div className="flex items-center gap-3">
                        <span className="opacity-60">{iconEl(child.icon, 18)}</span>
                        <span className="text-xs font-medium">{child.label}</span>
                      </div>
                      {child.badge && <Badge type={child.badge} />}
                    </button>
                  );
                })}
              </nav>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SidebarNav;
