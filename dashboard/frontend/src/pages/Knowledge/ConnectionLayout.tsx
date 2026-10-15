// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
import { NavLink, Outlet, useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Database } from 'lucide-react'
import { useEffect } from 'react'
import { KnowledgeProvider, useKnowledge } from '../../context/KnowledgeContext'
import { useAuth } from '../../context/AuthContext'

type Tab = { to: (cid: string) => string; label: string; exact?: boolean }

const tabs: Tab[] = [
  { to: (cid) => `/knowledge/connections/${cid}`, label: 'Overview', exact: true },
  { to: (cid) => `/knowledge/connections/${cid}/spaces`, label: 'Spaces' },
  { to: (cid) => `/knowledge/connections/${cid}/units`, label: 'Units' },
  { to: (cid) => `/knowledge/connections/${cid}/upload`, label: 'Upload' },
  { to: (cid) => `/knowledge/connections/${cid}/browse`, label: 'Browse' },
  { to: (cid) => `/knowledge/connections/${cid}/search`, label: 'Search' },
  { to: (cid) => `/knowledge/connections/${cid}/api-keys`, label: 'API Keys' },
]

function ConnectionLayoutInner() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { connections, activeConnectionId, setActiveConnectionId, loading } = useKnowledge()

  // Sync URL param → active connection context.
  useEffect(() => {
    if (id && id !== activeConnectionId) {
      setActiveConnectionId(id)
    }
  }, [id, activeConnectionId, setActiveConnectionId])

  const connection = connections.find((c) => c.id === id)

  // Initial load: defer "not found" verdict until the context has actually
  // fetched the connections list. Otherwise we flash the error on every
  // page refresh that lands directly on /knowledge/connections/:id.
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-[color:var(--text-muted)] text-sm">
        Loading connection…
      </div>
    )
  }

  if (!connection) {
    return (
      <div className="text-center py-16">
        <p className="text-[color:var(--text-secondary)] font-medium mb-2">Connection not found</p>
        <p className="text-[color:var(--text-muted)] text-sm mb-4">
          The connection you&apos;re trying to open doesn&apos;t exist or was deleted.
        </p>
        <button
          onClick={() => navigate('/knowledge')}
          className="text-sm text-[color:var(--evo-green)] hover:underline"
        >
          ← Back to Connections
        </button>
      </div>
    )
  }

  const statusColor =
    connection.status === 'ready'
      ? 'text-[color:var(--evo-green)] bg-[color:var(--evo-green)]/10'
      : connection.status === 'error'
      ? 'text-red-400 bg-red-400/10'
      : 'text-yellow-400 bg-yellow-400/10'

  return (
    <div>
      {/* Breadcrumb + header */}
      <div className="mb-6">
        <Link
          to="/knowledge"
          className="inline-flex items-center gap-1.5 text-xs text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)] mb-3 transition-colors"
        >
          <ArrowLeft size={14} />
          All connections
        </Link>
        <div className="flex items-center gap-3 flex-wrap">
          <Database size={20} className="text-[color:var(--evo-green)]" />
          <h1 className="text-xl font-bold text-[color:var(--text-primary)]">{connection.name}</h1>
          <span className={`text-[10px] px-2 py-0.5 rounded uppercase font-semibold ${statusColor}`}>
            {connection.status}
          </span>
          <span className="text-xs text-[color:var(--text-muted)] font-mono">
            {connection.host}:{connection.port ?? 5432} / {connection.database_name}
          </span>
        </div>
      </div>

      {/* Per-connection tabs */}
      <div className="flex gap-1 mb-6 border-b border-[color:var(--border)] overflow-x-auto">
        {tabs.map((t) => (
          <NavLink
            key={t.label}
            to={t.to(connection.id)}
            end={t.exact}
            className={({ isActive }) =>
              `px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                isActive
                  ? 'text-[color:var(--evo-green)] border-[color:var(--evo-green)]'
                  : 'text-[color:var(--text-muted)] border-transparent hover:text-[color:var(--text-secondary)]'
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </div>

      {/* Page content */}
      <Outlet />
    </div>
  )
}

export default function ConnectionLayout() {
  const { hasPermission } = useAuth()
  if (!hasPermission('knowledge', 'view')) {
    return (
      <div className="flex items-center justify-center h-64 text-[color:var(--text-muted)] text-sm">
        You don&apos;t have permission to view Knowledge.
      </div>
    )
  }
  return (
    <KnowledgeProvider>
      <ConnectionLayoutInner />
    </KnowledgeProvider>
  )
}
