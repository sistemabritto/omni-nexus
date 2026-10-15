// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

export function FullPageLoader({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[color:var(--bg-primary)] px-6">
      <div className="flex items-center gap-3 rounded-full border border-[color:var(--border)] bg-[color:var(--bg-card)] px-4 py-3 text-sm text-[color:var(--text-secondary)] shadow-[0_12px_40px_rgba(0,0,0,0.35)]">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-[color:var(--evo-green)]/25 border-t-[color:var(--evo-green)]" />
        <span>{label}</span>
      </div>
    </div>
  )
}

export function SectionLoader({ label = 'Loading section...' }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center px-6 py-12">
      <div className="flex items-center gap-3 rounded-2xl border border-[color:var(--border)] bg-[color:var(--bg-card)] px-4 py-3 text-sm text-[color:var(--text-secondary)] shadow-[0_12px_40px_rgba(0,0,0,0.25)]">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-[color:var(--evo-green)]/25 border-t-[color:var(--evo-green)]" />
        <span>{label}</span>
      </div>
    </div>
  )
}

interface SectionBoundaryProps {
  sectionName: string
  children: ReactNode
}

interface SectionBoundaryState {
  hasError: boolean
  error: Error | null
}

export class SectionBoundary extends Component<SectionBoundaryProps, SectionBoundaryState> {
  state: SectionBoundaryState = {
    hasError: false,
    error: null,
  }

  static getDerivedStateFromError(error: Error): SectionBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ui] ${this.props.sectionName} failed to render`, error, info)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[40vh] items-center justify-center px-6 py-12">
          <div className="w-full max-w-2xl rounded-3xl border border-red-500/20 bg-[color:var(--bg-card)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.45)]">
            <div className="flex items-center gap-3 text-red-300">
              <AlertTriangle size={18} />
              <div>
                <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                  Unable to load {this.props.sectionName}
                </h2>
                <p className="text-sm text-[color:var(--text-secondary)]">
                  An unexpected error interrupted this section.
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-2xl border border-[color:var(--border)] bg-[color:var(--bg-primary)] p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
                Error details
              </p>
              <p className="mt-2 text-sm text-[#FCA5A5] break-words">
                {this.state.error?.message || 'Unknown render failure'}
              </p>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={this.handleRetry}
                className="inline-flex items-center gap-2 rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-card)] px-4 py-2 text-sm font-medium text-[color:var(--text-primary)] transition-colors hover:border-[color:var(--evo-green)]/50 hover:text-white"
              >
                <RefreshCw size={14} />
                Try again
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-2 rounded-xl border border-[color:var(--evo-green)]/30 bg-[color:var(--evo-green)]/10 px-4 py-2 text-sm font-medium text-[color:var(--evo-green)] transition-colors hover:bg-[color:var(--evo-green)]/15"
              >
                Reload app
              </button>
            </div>
          </div>
        </div>
      )
    }

    return <>{this.props.children}</>
  }
}
