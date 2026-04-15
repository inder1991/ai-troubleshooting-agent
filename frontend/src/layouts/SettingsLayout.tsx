import { NavLink, Outlet } from 'react-router-dom';

const settingsNav = [
  { to: '/settings', label: 'Settings', icon: 'settings', end: true },
  { to: '/settings/integrations', label: 'Integrations', icon: 'hub' },
];

export default function SettingsLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {settingsNav.map(({ to, label, icon, end }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-duck-accent/10 text-duck-accent' : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'}`}
          >
            <span className="material-symbols-outlined text-[16px]" aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-hidden"><Outlet /></div>
    </div>
  );
}
