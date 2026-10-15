// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { useEffect, useState, useRef } from 'react'
import { ChevronDown, Circle, AlertTriangle, XCircle, Wifi } from 'lucide-react'
import { useKnowledge, type KnowledgeConnection } from '../../context/KnowledgeContext'

function StatusIcon({ status }: { status: KnowledgeConnection['status'] }) {
  if (status === 'ready')
    return <Circle size={8} className="fill-[color:var(--evo-green)] text-[color:var(--evo-green)]" />
  if (status === 'needs_migration')
    return <AlertTriangle size={10} className="text-yellow-400" />
  if (status === 'error')
    return <XCircle size={10} className="text-red-400" />
  return <Wifi size={10} className="text-[color:var(--text-muted)]" />
}

export default function ConnectionSwitcher() {
  const { activeConnectionId, setActiveConnectionId, connections, refreshConnections } = useKnowledge()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    refreshConnections()
  }, [refreshConnections])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = connections.find((c) => c.id === activeConnectionId)

  if (connections.length === 0) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg text-xs text-[color:var(--text-muted)]">
        <Wifi size={12} />
        No connections — add one below
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-1.5 bg-[color:var(--bg-card)] border border-[color:var(--border)] rounded-lg text-sm font-medium text-[color:var(--text-secondary)] hover:border-[color:var(--evo-green)]/50 transition-colors min-w-[180px]"
      >
        {active ? (
          <>
            <StatusIcon status={active.status} />
            <span className="flex-1 text-left truncate">{active.name}</span>
          </>
        ) : (
          <span className="flex-1 text-left text-[color:var(--text-muted)]">Select connection</span>
        )}
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-[color:var(--bg-primary)] border border-[color:var(--border)] rounded-lg shadow-lg z-50 py-1 min-w-[220px]">
          {connections.map((c) => (
            <button
              key={c.id}
              onClick={() => { setActiveConnectionId(c.id); setOpen(false) }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-white/5 ${
                c.id === activeConnectionId ? 'text-[color:var(--evo-green)]' : 'text-[color:var(--text-secondary)]'
              }`}
            >
              <StatusIcon status={c.status} />
              <span className="flex-1 text-left truncate">{c.name}</span>
              {c.id === activeConnectionId && (
                <span className="text-[10px] text-[color:var(--evo-green)]">active</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
