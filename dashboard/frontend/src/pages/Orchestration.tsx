import { useState, useEffect, useCallback } from 'react'
import {
  RefreshCw, XCircle, CheckCircle2, AlertTriangle, Clock, Play, Pause,
  FileText, ChevronDown, ChevronUp, Search,
  RotateCcw, Loader2, Bot, FolderKanban, Users, Zap,
} from 'lucide-react'

// Sem `date-fns` (não é dependência do projeto — instalar um pacote inteiro
// para produzir uma string de tempo relativo não se paga) e sem o `evo` do
// evonexus-sdk, que nunca exportou esse símbolo. O padrão de acesso à API é o
// mesmo de Pautas.tsx e das outras páginas: fetch com credentials.
const API = import.meta.env.DEV ? 'http://localhost:8080' : ''

async function apiCall(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: { 'X-Requested-With': 'XMLHttpRequest', ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (data?.error) msg = data.error
    } catch { /* resposta sem corpo JSON */ }
    throw new Error(msg)
  }
  return res.json()
}

/** "há 3 minutos" sem dependência externa. Intl.RelativeTimeFormat é nativo. */
function tempoRelativo(iso: string): string {
  const rtf = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' })
  const segundos = (new Date(iso).getTime() - Date.now()) / 1000
  const faixas: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000], ['month', 2592000], ['day', 86400],
    ['hour', 3600], ['minute', 60], ['second', 1],
  ]
  for (const [unidade, tamanho] of faixas) {
    if (Math.abs(segundos) >= tamanho || unidade === 'second') {
      return rtf.format(Math.round(segundos / tamanho), unidade)
    }
  }
  return ''
}

interface OrchestrationJob {
  id: string
  agent: string
  prompt: string
  stage: string
  stage_result: string | null
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  error: string | null
  telegram_chat_id: string | null
  telegram_message_id: string | null
  created_at: string | null
  updated_at: string | null
  started_at: string | null
  completed_at: string | null
}

interface JobsResponse {
  jobs: OrchestrationJob[]
}

const STATUS_LABELS: Record<string, { label: string; icon: React.ComponentType<{ size?: number }>; color: string }> = {
  pending: { label: 'Aguardando', icon: Clock, color: 'text-yellow-400' },
  running: { label: 'Executando', icon: Loader2, color: 'text-blue-400 animate-spin' },
  success: { label: 'Sucesso', icon: CheckCircle2, color: 'text-green-400' },
  failed: { label: 'Falha', icon: AlertTriangle, color: 'text-red-400' },
  cancelled: { label: 'Cancelado', icon: XCircle, color: 'text-gray-400' },
}

const STAGE_LABELS: Record<string, string> = {
  start: 'Início',
  research: 'Pesquisa',
  draft: 'Redação',
  review: 'Revisão',
  plan: 'Planejamento',
  breakdown: 'Quebra de tarefas',
  analyze: 'Análise',
  respond: 'Resposta',
  execute: 'Execução',
  done: 'Concluído',
}

const AGENT_LABELS: Record<string, { label: string; icon: React.ComponentType<{ size?: number }> }> = {
  ops: { label: 'Ops', icon: Bot },
  projects: { label: 'Projetos', icon: FolderKanban },
  community: { label: 'Comunidade', icon: Users },
  default: { label: 'Agente', icon: Zap },
}


function StatusBadge({ status }: { status: string }) {
  const s = STATUS_LABELS[status] || { label: status, icon: Clock, color: 'text-gray-400' }
  const Icon = s.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${s.color}`}>
      <Icon size={10} />
      {s.label}
    </span>
  )
}

function StageBadge({ stage }: { stage: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-[#667085] bg-white/5">
      {STAGE_LABELS[stage] || stage}
    </span>
  )
}

function AgentBadge({ agent }: { agent: string }) {
  const a = AGENT_LABELS[agent] || { label: agent, icon: Zap }
  const Icon = a.icon
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-[#D0D5DD] bg-white/5">
      <Icon size={10} />
      {a.label}
    </span>
  )
}

function RelativeTime({ dateStr }: { dateStr: string | null }) {
  if (!dateStr) return <span className="text-[#667085] text-xs">—</span>
  try {
    return <span className="text-[#667085] text-xs" title={dateStr}>{tempoRelativo(dateStr)}</span>
  } catch {
    return <span className="text-[#667085] text-xs">{dateStr}</span>
  }
}

export default function OrchestrationPage() {
  const [jobs, setJobs] = useState<OrchestrationJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedJob, setExpandedJob] = useState<string | null>(null)
  const [logs, setLogs] = useState<Record<string, string>>({})
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterAgent, setFilterAgent] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const fetchJobs = useCallback(async () => {
    try {
      setError(null)
      const data: JobsResponse = await apiCall('/api/orchestration-jobs')
      setJobs(data?.jobs || [])
    } catch (err: any) {
      setError(err.message || 'Erro ao carregar jobs')
      console.error('[OrchestrationPage] fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchLogs = useCallback(async (jobId: string) => {
    try {
      const data: { job: OrchestrationJob; logs: string } = await apiCall(`/api/orchestration-jobs/${jobId}`)
      setLogs(prev => ({ ...prev, [jobId]: data.logs || '' }))
    } catch (err) {
      console.error('[OrchestrationPage] logs error:', err)
    }
  }, [])

  const handleCancel = async (jobId: string) => {
    if (!confirm('Cancelar este job?')) return
    try {
      await apiCall(`/api/orchestration-jobs/${jobId}/cancel`, { method: 'POST' })
      fetchJobs()
    } catch (err: any) {
      alert(err.message || 'Erro ao cancelar')
    }
  }

  const handleRetry = (jobId: string) => {
    // Não recria o job a partir daqui de propósito: `to_dict()` devolve o
    // prompt TRUNCADO em 200 caracteres, então um POST com esse texto rodaria
    // uma tarefa diferente da original sem avisar ninguém. Reexecutar tem de
    // partir do prompt inteiro, que só existe no chat de origem.
    alert(
      `Job ${jobId} não é reexecutado daqui: a API devolve o prompt cortado em ` +
      `200 caracteres e reenviá-lo rodaria outra tarefa. Dispare de novo pelo ` +
      `/ops no Telegram, com o texto original.`
    )
  }

  const handleToggleExpand = (jobId: string) => {
    setExpandedJob(prev => prev === jobId ? null : jobId)
    if (expandedJob !== jobId) {
      fetchLogs(jobId)
    }
  }

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000) // Poll a cada 5s
    return () => clearInterval(interval)
  }, [fetchJobs])

  const filteredJobs = jobs.filter(job => {
    if (filterStatus !== 'all' && job.status !== filterStatus) return false
    if (filterAgent !== 'all' && job.agent !== filterAgent) return false
    if (searchQuery && !job.prompt.toLowerCase().includes(searchQuery.toLowerCase()) && 
        !job.id.toLowerCase().includes(searchQuery.toLowerCase())) return false
    return true
  })

  const agents = [...new Set(jobs.map(j => j.agent))]

  if (loading && jobs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-[#00FFA7]" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 text-center text-red-400">
        <AlertTriangle className="h-12 w-12 mx-auto mb-4" />
        <p>{error}</p>
        <button onClick={fetchJobs} className="mt-4 px-4 py-2 bg-[#00FFA7]/10 text-[#00FFA7] rounded hover:bg-[#00FFA7]/20">
          Tentar novamente
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Orquestração</h1>
          <p className="text-[#667085] mt-1">Acompanhe jobs multi-agente disparados via Telegram/Chat</p>
        </div>
        <button onClick={fetchJobs} className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-medium text-[#D0D5DD] border border-[#344054]">
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 bg-[#131a2a] border border-[#344054] rounded-lg p-4">
        <div className="flex-1 min-w-[200px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#667085]" />
          <input
            type="text"
            placeholder="Buscar por ID ou prompt..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-[#0C111D] border border-[#344054] rounded-lg text-white placeholder-[#667085] focus:outline-none focus:border-[#00FFA7] focus:ring-1 focus:ring-[#00FFA7]"
          />
        </div>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          className="px-3 py-2 bg-[#0C111D] border border-[#344054] rounded-lg text-white text-sm focus:outline-none focus:border-[#00FFA7]"
        >
          <option value="all">Todos os status</option>
          <option value="pending">Aguardando</option>
          <option value="running">Executando</option>
          <option value="success">Sucesso</option>
          <option value="failed">Falha</option>
          <option value="cancelled">Cancelado</option>
        </select>
        <select
          value={filterAgent}
          onChange={e => setFilterAgent(e.target.value)}
          className="px-3 py-2 bg-[#0C111D] border border-[#344054] rounded-lg text-white text-sm focus:outline-none focus:border-[#00FFA7]"
        >
          <option value="all">Todos os agentes</option>
          {agents.map(a => <option key={a} value={a}>{AGENT_LABELS[a]?.label || a}</option>)}
        </select>
      </div>

      {/* Jobs List */}
      <div className="bg-[#131a2a] border border-[#344054] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#344054] bg-[#0C111D]/50">
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">ID</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Agente</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Prompt</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Etapa</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Status</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Iniciado</th>
                <th className="px-4 py-3 text-left text-[10px] uppercase tracking-wider text-[#667085] font-semibold">Concluído</th>
                <th className="px-4 py-3 text-right text-[10px] uppercase tracking-wider text-[#667085] font-semibold pr-4">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-[#667085]">
                    {jobs.length === 0 ? 'Nenhum job ainda. Use /ops no Telegram para criar um.' : 'Nenhum job corresponde aos filtros.'}
                  </td>
                </tr>
              ) : (
                filteredJobs.map(job => (
                  <tr key={job.id} className="border-b border-[#344054]/50 hover:bg-white/5 transition-colors cursor-pointer" onClick={() => handleToggleExpand(job.id)}>
                    <td className="px-4 py-3 font-mono text-xs text-[#888]">{job.id.slice(0, 12)}…</td>
                    <td className="px-4 py-3"><AgentBadge agent={job.agent} /></td>
                    <td className="px-4 py-3 max-w-[300px] truncate text-[#D0D5DD]" title={job.prompt}>{job.prompt}</td>
                    <td className="px-4 py-3"><StageBadge stage={job.stage} /></td>
                    <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                    <td className="px-4 py-3"><RelativeTime dateStr={job.started_at} /></td>
                    <td className="px-4 py-3"><RelativeTime dateStr={job.completed_at} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {job.status === 'running' && (
                          <button onClick={e => { e.stopPropagation(); handleCancel(job.id) }} className="p-1.5 text-red-400 hover:bg-red-500/10 rounded" title="Cancelar">
                            <Pause className="h-4 w-4" />
                          </button>
                        )}
                        {job.status === 'failed' && (
                          <button onClick={e => { e.stopPropagation(); handleRetry(job.id) }} className="p-1.5 text-yellow-400 hover:bg-yellow-500/10 rounded" title="Retry">
                            <RotateCcw className="h-4 w-4" />
                          </button>
                        )}
                        {(job.status === 'success' || job.status === 'failed') && (
                          <button onClick={e => { e.stopPropagation(); handleToggleExpand(job.id) }} className="p-1.5 text-[#667085] hover:text-[#D0D5DD] hover:bg-white/10 rounded" title={expandedJob === job.id ? 'Recolher' : 'Expandir'}>
                            {expandedJob === job.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Expanded Logs */}
        {expandedJob && logs[expandedJob] && (
          <div className="border-t border-[#344054] bg-[#0C111D]/50 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-[#D0D5DD] font-mono">Logs — {expandedJob.slice(0, 12)}…</span>
              <button onClick={() => setExpandedJob(null)} className="p-1 text-[#667085] hover:text-[#D0D5DD]">
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <pre className="bg-[#080c14] border border-[#344054] rounded p-3 max-h-96 overflow-auto text-xs text-[#888] font-mono whitespace-pre-wrap">
              {logs[expandedJob] || 'Sem logs disponíveis'}
            </pre>
          </div>
        )}
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Total" value={jobs.length} icon={FileText} color="text-[#667085]" />
        <StatCard label="Executando" value={jobs.filter(j => j.status === 'running').length} icon={Play} color="text-blue-400" />
        <StatCard label="Sucesso" value={jobs.filter(j => j.status === 'success').length} icon={CheckCircle2} color="text-green-400" />
        <StatCard label="Falha" value={jobs.filter(j => j.status === 'failed').length} icon={AlertTriangle} color="text-red-400" />
        <StatCard label="Aguardando" value={jobs.filter(j => j.status === 'pending').length} icon={Clock} color="text-yellow-400" />
      </div>
    </div>
  )
}

function StatCard({ label, value, icon: Icon, color }: { label: string; value: number; icon: React.ComponentType<{ size?: number }>; color: string }) {
  return (
    <div className="bg-[#131a2a] border border-[#344054] rounded-lg p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-[#667085]">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
        </div>
        <div className={`${color} bg-current/10 p-3 rounded-lg`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  )
}