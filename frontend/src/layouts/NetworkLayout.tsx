import { NavLink, Outlet } from 'react-router-dom';

const networkNav = [
  { to: '/network/topology', label: 'Topology', icon: 'device_hub' },
  { to: '/network/adapters', label: 'Adapters', icon: 'settings_input_component' },
  { to: '/network/monitoring', label: 'Devices', icon: 'router' },
  { to: '/network/ipam', label: 'IPAM', icon: 'dns' },
  { to: '/network/flows', label: 'Flows', icon: 'grid_view' },
  { to: '/network/observatory', label: 'Observatory', icon: 'monitoring' },
  { to: '/network/mib-browser', label: 'MIB Browser', icon: 'manage_search' },
  { to: '/network/cloud', label: 'Cloud', icon: 'cloud' },
  { to: '/network/security', label: 'Security', icon: 'security' },
];

export default function NetworkLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {networkNav.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? 'bg-duck-accent/10 text-duck-accent'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`
            }
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
