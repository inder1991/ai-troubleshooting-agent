// Q17 alpha — every route wrapped in <ErrorBoundary>; per-card boundaries
// inside the war room. Errors propagate to the error reporter (Q16).

import { Component, type ErrorInfo, type ReactNode } from "react";

import { errorReporter } from "@/lib/errorReporter";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  scope?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    errorReporter.captureException(error, {
      event: "react_render_error",
      route: typeof window !== "undefined" ? window.location.pathname : undefined,
      scope: this.props.scope,
      componentStack: info.componentStack ?? undefined,
    });
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      const { fallback } = this.props;
      return typeof fallback === "function"
        ? fallback(this.state.error, this.reset)
        : fallback;
    }
    return this.props.children;
  }
}
