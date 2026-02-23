import React from 'react';

interface ErrorBannerProps {
  message: string;
  severity?: 'error' | 'warning';
  onDismiss?: () => void;
  onRetry?: () => void;
}

const ErrorBanner: React.FC<ErrorBannerProps> = ({
  message,
  severity = 'error',
  onDismiss,
  onRetry,
}) => {
  const isError = severity === 'error';
  const bgClass = isError
    ? 'bg-red-500/10 border-red-500/20'
    : 'bg-amber-500/10 border-amber-500/20';
  const textClass = isError ? 'text-red-400' : 'text-amber-400';
  const icon = isError ? 'error' : 'warning';

  return (
    <div className={`flex items-center gap-2.5 px-4 py-2.5 border rounded-lg ${bgClass}`} role="alert">
      <span
        className={`material-symbols-outlined text-base ${textClass} shrink-0`}
        style={{ fontFamily: 'Material Symbols Outlined' }}
      >
        {icon}
      </span>
      <span className={`text-[11px] ${textClass} flex-1`}>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className={`text-[10px] font-bold px-2.5 py-1 rounded border ${
            isError
              ? 'bg-red-500/20 text-red-400 border-red-500/30 hover:bg-red-500/30'
              : 'bg-amber-500/20 text-amber-400 border-amber-500/30 hover:bg-amber-500/30'
          } transition-colors`}
          aria-label="Retry"
        >
          Retry
        </button>
      )}
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-slate-500 hover:text-slate-300 transition-colors p-0.5"
          aria-label="Dismiss"
        >
          <span
            className="material-symbols-outlined text-sm"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            close
          </span>
        </button>
      )}
    </div>
  );
};

export default ErrorBanner;
