import React from 'react';

interface Props {
  tabName: string;
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class NDMErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[NDM ${this.props.tabName}] Render error:`, error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: 32,
            textAlign: 'center',
            background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 10,
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: 32, color: '#ef4444', marginBottom: 12, display: 'block' }}
          >
            error
          </span>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 6 }}>
            {this.props.tabName} encountered an error
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 16 }}>
            {this.state.error?.message || 'An unexpected error occurred'}
          </div>
          <button
            onClick={this.handleRetry}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              border: '1px solid rgba(7,182,213,0.3)',
              background: 'rgba(7,182,213,0.1)',
              color: '#07b6d5',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default NDMErrorBoundary;
