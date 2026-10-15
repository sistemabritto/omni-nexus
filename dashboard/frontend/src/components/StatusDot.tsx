// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
interface StatusDotProps {
  status: 'ok' | 'error' | 'pending'
}

export default function StatusDot({ status }: StatusDotProps) {
  const color = {
    ok: 'bg-[color:var(--evo-green)]',
    error: 'bg-red-400',
    pending: 'bg-yellow-400',
  }[status]

  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />
  )
}
