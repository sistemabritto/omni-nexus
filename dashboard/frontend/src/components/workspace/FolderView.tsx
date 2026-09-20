import { useEffect, useState } from 'react'
import { ChevronRight, FileText, Folder, FolderOpen, Loader2 } from 'lucide-react'
import { api } from '../../lib/api'

// View de pasta para a aba Arquivos do Materiais: ao selecionar uma pasta,
// lista o conteúdo (pastas primeiro, depois arquivos) em vez da mensagem
// "selecione um arquivo". Clique em pasta navega; clique em arquivo abre.

interface Entry {
  name: string
  path: string
  is_dir: boolean
  size?: number
  modified?: number
}

interface Breadcrumb {
  name: string
  path: string
}

interface Props {
  dirPath: string
  onOpenFile: (path: string) => void
  onOpenDir: (path: string) => void
  refreshTrigger: number
}

function formatSize(bytes?: number): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function FolderView({ dirPath, onOpenFile, onOpenDir, refreshTrigger }: Props) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [breadcrumbs, setBreadcrumbs] = useState<Breadcrumb[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect — loading inicial (mesmo padrão do Workspace.tsx)
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const data = await api.get(`/workspace/tree?path=${encodeURIComponent(dirPath)}&depth=1`)
        if (cancelled) return
        setEntries(Array.isArray(data.entries) ? data.entries : [])
        setBreadcrumbs(Array.isArray(data.breadcrumbs) ? data.breadcrumbs : [])
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Erro ao carregar pasta')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [dirPath, refreshTrigger])

  return (
    <div className="h-full overflow-auto" style={{ background: 'var(--bg-primary)' }}>
      <div className="p-4 lg:p-6 max-w-5xl mx-auto">
        {/* Breadcrumbs */}
        {breadcrumbs.length > 0 && (
          <nav aria-label="breadcrumb" className="flex items-center flex-wrap gap-1 mb-4 text-sm">
            <button
              onClick={() => onOpenDir('workspace')}
              className="px-2 py-1 rounded-md cursor-pointer transition-colors"
              style={{ color: 'var(--evo-green)', background: 'var(--bg-card)' }}
            >
              workspace
            </button>
            {breadcrumbs.slice(1).map((b) => (
              <span key={b.path} className="flex items-center gap-1">
                <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
                <button
                  onClick={() => onOpenDir(b.path)}
                  className="px-2 py-1 rounded-md cursor-pointer transition-colors hover:opacity-80"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {b.name}
                </button>
              </span>
            ))}
          </nav>
        )}

        {/* Title */}
        <div className="flex items-center gap-2 mb-4">
          <FolderOpen size={18} style={{ color: 'var(--evo-green)' }} />
          <h2 className="text-base font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
            {dirPath.split('/').pop()}
          </h2>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
          </div>
        )}

        {!loading && error && (
          <div className="py-16 text-center text-sm" style={{ color: 'var(--danger)' }}>{error}</div>
        )}

        {!loading && !error && entries.length === 0 && (
          <div className="py-16 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            Pasta vazia
          </div>
        )}

        {!loading && !error && entries.length > 0 && (
          <div
            className="rounded-xl overflow-hidden"
            style={{ border: '1px solid var(--border)', background: 'var(--bg-card)' }}
          >
            <div
              className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2 text-xs font-medium border-b"
              style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
            >
              <span>Nome</span>
              <span className="w-24 text-right">Tamanho</span>
              <span className="w-32 text-right">Modificado</span>
            </div>
            {entries.map((e) => (
              <button
                key={e.path}
                onClick={() => (e.is_dir ? onOpenDir(e.path) : onOpenFile(e.path))}
                title={e.path}
                className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2.5 w-full text-left items-center transition-colors cursor-pointer"
                style={{
                  background: 'transparent',
                  borderBottom: e === entries[entries.length - 1] ? 'none' : '1px solid var(--border)',
                }}
                onMouseEnter={(ev) => { ev.currentTarget.style.background = 'var(--surface-hover)' }}
                onMouseLeave={(ev) => { ev.currentTarget.style.background = 'transparent' }}
              >
                <span className="flex items-center gap-2 min-w-0">
                  {e.is_dir ? (
                    <Folder size={16} style={{ color: 'var(--warning)' }} />
                  ) : (
                    <FileText size={16} style={{ color: 'var(--text-secondary)' }} />
                  )}
                  <span className="truncate text-sm" style={{ color: 'var(--text-primary)' }}>{e.name}</span>
                </span>
                <span className="w-24 text-right text-xs tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  {e.is_dir ? '—' : formatSize(e.size)}
                </span>
                <span className="w-32 text-right text-xs tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  {formatDate(e.modified)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
