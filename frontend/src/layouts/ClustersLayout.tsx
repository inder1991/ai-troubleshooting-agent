import { NavLink, Outlet } from 'react-router-dom';

const clustersNav = [
  { to: '/clusters', label: 'Clusters', icon: 'deployed_code', end: true },
  { to: '/clusters/registry', label: 'Fleet', icon: 'cloud_circle' },
  { to: '/clusters/recommendations', label: 'Recommendations', icon: 'tips_and_updates' },
];

export default function ClustersLayout() {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-duck-border/20 bg-[#13110d]/50 overflow-x-auto">
        {clustersNav.map(({ to, label, icon, end }) => (
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
