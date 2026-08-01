import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangleIcon, RotateCcwIcon } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  handleRetry = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen w-screen flex items-center justify-center bg-[#0a0a0b]">
          <div className="max-w-md w-full mx-4 bg-[rgba(18,20,22,0.8)] border border-white/10 rounded-2xl p-8 shadow-2xl backdrop-blur-xl text-center">
            {/* Error Icon */}
            <div className="flex justify-center mb-6">
              <div className="rounded-full bg-rose-500/15 p-4">
                <AlertTriangleIcon className="w-10 h-10 text-rose-400" />
              </div>
            </div>

            <h2 className="text-white text-xl font-medium mb-2">
              Something went wrong
            </h2>
            <p className="text-white/50 text-sm font-light mb-6 max-w-xs mx-auto leading-relaxed">
              An unexpected error occurred. Please try reloading the dashboard.
            </p>

            {/* Error Details (collapsed by default) */}
            {this.state.error && (
              <details className="mb-6 text-left">
                <summary className="text-white/40 text-xs cursor-pointer hover:text-white/60 transition-colors mb-2">
                  Error details
                </summary>
                <pre className="text-[10px] text-rose-400/80 bg-black/40 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-32 overflow-y-auto">
                  {this.state.error.toString()}
                </pre>
              </details>
            )}

            {/* Retry Button */}
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-2 px-6 py-3 bg-white/10 hover:bg-white/15 border border-white/10 rounded-xl text-white text-sm font-medium transition-colors"
            >
              <RotateCcwIcon className="w-4 h-4" />
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
