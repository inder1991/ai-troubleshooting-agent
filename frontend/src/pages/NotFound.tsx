import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 text-slate-300">
      <span
        className="material-symbols-outlined text-7xl text-slate-400"
        aria-hidden="true"
      >
        explore_off
      </span>
      <h1 className="text-2xl font-display font-bold text-slate-100">
        Page not found
      </h1>
      <p className="text-sm text-slate-400 max-w-md text-center">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Link
        to="/"
        className="px-4 py-2 rounded-lg bg-duck-accent/20 text-duck-accent text-sm font-medium hover:bg-duck-accent/30 transition-colors"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
