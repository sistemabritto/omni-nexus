// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: string | number
  delta?: string
  deltaType?: 'up' | 'down' | 'neutral'
}

export default function MetricCard({ label, value, delta, deltaType = 'neutral' }: MetricCardProps) {
  const deltaColor = {
    up: 'text-[color:var(--evo-green)]',
    down: 'text-red-400',
    neutral: 'text-[color:var(--text-muted)]',
  }[deltaType]

  const DeltaIcon = {
    up: TrendingUp,
    down: TrendingDown,
    neutral: Minus,
  }[deltaType]

  return (
    <div className="bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-xl p-5 hover:border-[color:var(--evo-green)] transition-colors">
      <p className="text-sm text-[color:var(--text-muted)] mb-1">{label}</p>
      <p className="text-2xl font-bold text-[color:var(--text-primary)]">{value}</p>
      {delta && (
        <div className={`flex items-center gap-1 mt-2 text-xs ${deltaColor}`}>
          <DeltaIcon size={14} />
          <span>{delta}</span>
        </div>
      )}
    </div>
  )
}
