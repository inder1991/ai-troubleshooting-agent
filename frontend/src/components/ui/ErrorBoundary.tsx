import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary] Caught render error:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleRecover = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex items-center justify-center h-full min-h-[400px]" style={{ backgroundColor: '#0f2023' }}>
          <div className="max-w-md text-center p-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <span
                className="material-symbols-outlined text-red-400 text-3xl"
                style={{ fontFamily: 'Material Symbols Outlined' }}
              >
                error
              </span>
            </div>
            <h2 className="text-lg font-bold text-slate-200 mb-2">Something went wrong</h2>
            <p className="text-sm text-slate-400 mb-1">
              The investigation UI encountered an unexpected error.
            </p>
            {this.state.error && (
              <pre className="text-[10px] font-mono text-red-400/80 bg-red-500/5 border border-red-500/10 rounded-lg p-3 mt-3 mb-4 max-h-[120px] overflow-auto text-left">
                {this.state.error.message}
              </pre>
            )}
            <div className="flex items-center justify-center gap-3 mt-4">
              <button
                onClick={this.handleRecover}
                className="text-xs font-bold px-4 py-2 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 transition-colors"
              >
                Try to Recover
              </button>
              <button
                onClick={this.handleReload}
                className="text-xs font-bold px-4 py-2 rounded-lg bg-[#07b6d5]/20 text-[#07b6d5] border border-[#07b6d5]/30 hover:bg-[#07b6d5]/30 transition-colors"
              >
                Reload Page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
