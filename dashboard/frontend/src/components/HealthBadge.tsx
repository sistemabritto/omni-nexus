// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
interface HealthBadgeProps {
  status: 'healthy' | 'warning' | 'critical'
  label: string
}

export default function HealthBadge({ status, label }: HealthBadgeProps) {
  const styles = {
    healthy: 'bg-[color:var(--evo-green)]/15 text-[color:var(--evo-green)] border-[color:var(--evo-green)]/30',
    warning: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  }[status]

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${styles}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${
        status === 'healthy' ? 'bg-[color:var(--evo-green)]' : status === 'warning' ? 'bg-yellow-400' : 'bg-red-400'
      }`} />
      {label}
    </span>
  )
}
