// Modified 2026-10-15: OmniNexus Live global UI system; original EvoNexus attribution retained.
/**
 * McpServers.tsx — Wave 2.3 UI
 *
 * Read-only view of every MCP server configured for this workspace, from both
 * scopes the Claude Code CLI reads: `.mcp.json` at the repo root (project —
 * versioned in the fork, identical on every machine running the image) and
 * `~/.claude.json` (user — where the plugin installer injects, and what gets
 * wiped on each VPS redeploy).
 *
 * The page used to read only the user scope, so on the VPS it rendered empty
 * while ten servers were configured. It also only knew the stdio transport
 * (command + args) and showed "—" for every HTTP server — which is the
 * transport all of them actually use.
 *
 * Management of plugin MCPs happens implicitly via plugin install/uninstall.
 * Native entries are edited in the file itself — the source paths are listed
 * so the user knows which file to open.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Terminal, Package, AlertTriangle, ExternalLink, ChevronDown, ChevronUp, Copy,
  RefreshCw, Loader2, Globe,
} from 'lucide-react'
import HubBackLink from '../components/HubBackLink'
import { api } from '../lib/api'

interface McpServer {
  name: string
  transport: 'http' | 'sse' | 'stdio'
  url: string | null
  command: string | null
  args: string[]
  env: Record<string, string>
  scope: 'project' | 'user'
  source: 'plugin' | 'native'
  source_plugin: string | null
}

interface McpSource {
  scope: 'project' | 'user'
  path: string
  exists: boolean
  count: number
}

interface McpServersResponse {
  workspace: string
  claude_json_exists: boolean
  claude_json_path?: string
  sources?: McpSource[]
  servers: McpServer[]
  error?: string
}

const SCOPE_LABEL: Record<string, string> = { project: '.mcp.json', user: '~/.claude.json' }

function ServerCard({ server }: { server: McpServer }) {
  const [open, setOpen] = useState(false)
  const remoto = server.transport !== 'stdio'
  const argsStr = server.args.join(' ')
  const envKeys = Object.keys(server.env)
  const resumo = remoto ? server.url : `${server.command ?? '—'} ${argsStr}`.trim()

  return (
    <div className="border border-[color:var(--border)] rounded-xl bg-[color:var(--bg-primary)] overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
              server.source === 'plugin'
                ? 'bg-[color:var(--evo-green)]/10 text-[color:var(--evo-green)]'
                : 'bg-[color:var(--border)] text-[color:var(--text-muted)]'
            }`}
          >
            {server.source === 'plugin' ? <Package size={14} /> : remoto ? <Globe size={14} /> : <Terminal size={14} />}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-[color:var(--text-primary)] font-mono truncate">
                {server.name}
              </span>
              <span className="shrink-0 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[color:var(--border)] text-[color:var(--text-muted)]">
                {server.transport}
              </span>
              <span
                title={SCOPE_LABEL[server.scope]}
                className="shrink-0 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[color:var(--border)] text-[color:var(--text-muted)]"
              >
                {server.scope}
              </span>
              {server.source === 'plugin' && server.source_plugin && (
                <Link
                  to={`/plugins/${server.source_plugin}`}
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[color:var(--evo-green)]/10 text-[color:var(--evo-green)] border border-[color:var(--evo-green)]/20 hover:bg-[color:var(--evo-green)]/20"
                >
                  {server.source_plugin}
                </Link>
              )}
            </div>
            <p className="text-xs text-[color:var(--text-muted)] font-mono truncate mt-0.5">{resumo}</p>
          </div>
        </div>
        <div className="shrink-0 text-[color:var(--text-muted)]">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[color:var(--border)] px-4 py-3 space-y-3 bg-black/20">
          {remoto ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">Endpoint</p>
              <code className="block text-xs text-[color:var(--text-secondary)] font-mono bg-[color:var(--bg-card)] px-2 py-1.5 rounded border border-[color:var(--border)] break-all">
                {server.url ?? '(none)'}
              </code>
            </div>
          ) : (
            <>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">Command</p>
                <code className="block text-xs text-[color:var(--text-secondary)] font-mono bg-[color:var(--bg-card)] px-2 py-1.5 rounded border border-[color:var(--border)]">
                  {server.command ?? '(none)'}
                </code>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">
                  Args ({server.args.length})
                </p>
                {server.args.length === 0 ? (
                  <p className="text-xs text-[color:var(--text-muted)] italic">none</p>
                ) : (
                  <ul className="space-y-1">
                    {server.args.map((a, i) => (
                      <li
                        key={i}
                        className="text-xs text-[color:var(--text-secondary)] font-mono bg-[color:var(--bg-card)] px-2 py-1 rounded border border-[color:var(--border)] break-all"
                      >
                        {a}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">
              Environment ({envKeys.length})
            </p>
            {envKeys.length === 0 ? (
              <p className="text-xs text-[color:var(--text-muted)] italic">none</p>
            ) : (
              <ul className="space-y-1">
                {envKeys.map((k) => (
                  <li
                    key={k}
                    className="text-xs text-[color:var(--text-secondary)] font-mono bg-[color:var(--bg-card)] px-2 py-1 rounded border border-[color:var(--border)] break-all"
                  >
                    <span className="text-[color:var(--evo-green)]">{k}</span>
                    <span className="text-[color:var(--text-muted)]">=</span>
                    <span>{'•'.repeat(Math.min(8, server.env[k].length || 1))}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function McpServers() {
  const { t } = useTranslation()
  const [data, setData] = useState<McpServersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copiedPath, setCopiedPath] = useState<string | null>(null)

  async function fetchServers() {
    setLoading(true)
    setError(null)
    try {
      const result = (await api.get('/mcp-servers')) as McpServersResponse
      setData(result)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'unexpected error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchServers()
  }, [])

  async function copyPath(path: string) {
    try {
      await navigator.clipboard.writeText(path)
      setCopiedPath(path)
      setTimeout(() => setCopiedPath(null), 1500)
    } catch {
      // ignore
    }
  }

  const servers = data?.servers ?? []
  const sources = data?.sources ?? []
  const pluginServers = servers.filter((s) => s.source === 'plugin')
  const nativeServers = servers.filter((s) => s.source === 'native')

  // Group plugin servers by source_plugin
  const pluginGroups: Record<string, McpServer[]> = {}
  for (const s of pluginServers) {
    const key = s.source_plugin ?? '—'
    if (!pluginGroups[key]) pluginGroups[key] = []
    pluginGroups[key].push(s)
  }

  return (
    <div className="max-w-3xl mx-auto">
      <HubBackLink />
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-[color:var(--text-primary)] flex items-center gap-2">
            <Terminal size={22} className="text-[color:var(--evo-green)]" />
            {t('nav.mcpServers', 'MCP Servers')}
          </h1>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            {t('mcpServers.subtitle', 'MCP servers configured for this workspace — from .mcp.json (project) and ~/.claude.json (user).')}
          </p>
        </div>
        <button
          onClick={fetchServers}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-[color:var(--border)] text-[color:var(--text-secondary)] rounded-lg hover:bg-[#2a3139] disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {t('common.refresh', 'Refresh')}
        </button>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-[color:var(--text-muted)]">
          <Loader2 size={16} className="animate-spin" />
          {t('common.loading', 'Loading…')}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/5 border border-red-500/20 rounded-xl px-4 py-3 mb-4">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Config sources — both scopes, each with its own count */}
      {data && sources.length > 0 && (
        <div className="mb-6 border border-[color:var(--border)] rounded-xl bg-[color:var(--bg-primary)] divide-y divide-[color:var(--border)]">
          {sources.map((s) => (
            <div key={s.path} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-1">
                  {s.scope === 'project'
                    ? t('mcpServers.scopeProject', 'Project — versioned with the repo')
                    : t('mcpServers.scopeUser', 'User — per machine')}
                </p>
                <code className="text-xs text-[color:var(--text-secondary)] font-mono break-all">{s.path}</code>
              </div>
              <div className="shrink-0 flex items-center gap-2">
                <span className="text-xs text-[color:var(--text-muted)] tabular-nums">
                  {s.exists ? `${s.count}` : t('mcpServers.missing', 'absent')}
                </span>
                <button
                  onClick={() => copyPath(s.path)}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)] transition-colors"
                >
                  <Copy size={11} />
                  {copiedPath === s.path ? t('common.copied', 'Copied') : t('common.copy', 'Copy')}
                </button>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-[color:var(--text-muted)] px-4 py-2 flex items-center gap-1">
            <ExternalLink size={10} />
            {t('mcpServers.restartHint', 'Restart Claude Code CLI after any change.')}
          </p>
        </div>
      )}

      {/* Empty — nothing configured in either scope */}
      {data && servers.length === 0 && !loading && (
        <div className="text-center py-16 text-sm text-[color:var(--text-muted)]">
          <p>{t('mcpServers.empty', 'No MCP servers configured for this workspace yet.')}</p>
        </div>
      )}

      {/* Plugin servers */}
      {Object.keys(pluginGroups).length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-sm font-medium text-[color:var(--text-secondary)]">
              {t('mcpServers.fromPlugins', 'From plugins')}
            </h2>
            <span className="text-xs text-[color:var(--text-muted)]">({pluginServers.length})</span>
          </div>
          {Object.entries(pluginGroups).map(([pluginSlug, items]) => (
            <div key={pluginSlug} className="mb-4">
              <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)] mb-2 font-medium">
                {pluginSlug}
              </p>
              <div className="space-y-2">
                {items.map((s) => (
                  <ServerCard key={s.name} server={s} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Native / manual servers */}
      {nativeServers.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-sm font-medium text-[color:var(--text-secondary)]">
              {t('mcpServers.native', 'Native / manual')}
            </h2>
            <span className="text-xs text-[color:var(--text-muted)]">({nativeServers.length})</span>
          </div>
          <div className="space-y-2">
            {nativeServers.map((s) => (
              <ServerCard key={s.name} server={s} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
