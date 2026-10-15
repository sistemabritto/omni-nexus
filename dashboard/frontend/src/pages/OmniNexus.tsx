// OmniNexus UI added 2026-10-15. EvoNexus attribution and original console retained.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Bot, Brain, CheckCircle2, Layers3, MessageSquare, MicOff, Plus, RefreshCw, ShieldCheck } from 'lucide-react'
import AgentChat from '../components/AgentChat'
import Markdown from '../components/Markdown'
import { api } from '../lib/api'
import { TS_HTTP } from '../lib/terminal-url'
import './OmniNexus.css'

type Agent = { name: string; description?: string }
type Session = { id: string; name?: string; preview?: string; archived?: boolean; active?: boolean }
type Job = { id: string; agent: string; status: string; stage: string; prompt: string; error?: string }
type Source = { name: string; path: string }
const statusLabel: Record<string, string> = { pending: 'Na fila', running: 'Em execução', success: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' }
async function terminal(path: string, options?: RequestInit) {
  const response = await fetch(`${TS_HTTP}/api${path}`, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', ...options?.headers } })
  if (!response.ok) throw new Error(`Serviço de sessões: HTTP ${response.status}`)
  return response.json()
}
export default function OmniNexus() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [agent, setAgent] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [session, setSession] = useState<string | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [sourceText, setSourceText] = useState('')
  const [sourcePath, setSourcePath] = useState('')
  const sourceRequest = useRef(0)
  const [error, setError] = useState('')
  const [jobsError, setJobsError] = useState('')
  const [contextLoading, setContextLoading] = useState(true)
  const [memoryError, setMemoryError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [sessionToolsOpen, setSessionToolsOpen] = useState(false)
  const [approvals, setApprovals] = useState(0)
  const [tab, setTab] = useState<'jobs' | 'memory'>('jobs')
  useEffect(() => {
    let cancelled = false
    api.get('/agents').then((data: Agent[]) => {
      if (cancelled) return
      setAgents(data)
      const orchestrator = data.find(a => /orchestrat|orquestr|oracle/i.test(a.name))
      setAgent(orchestrator?.name || data[0]?.name || '')
    }).catch(() => { if (!cancelled) setError('Não foi possível carregar o squad. Verifique sua conexão e permissões.') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])
  useEffect(() => {
    let cancelled = false
    if (!agent) return
    terminal(`/sessions/by-agent/${encodeURIComponent(agent)}`).then(data => { if (!cancelled) { setSessions(data.sessions || []); setError('') } }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [agent])
  const loadContext = useCallback(() => {
    const jobsRequest = api.get('/orchestration-jobs').then(data => { setJobs(data.jobs || []); setJobsError('') }).catch(() => setJobsError('Jobs indisponíveis. Nenhum progresso pode ser confirmado.'))
    const memoryRequest = api.get('/memory').then(data => { setSources(data.global_files || []); setMemoryError('') }).catch(() => setMemoryError('Fontes de memória indisponíveis para este acesso.'))
    void Promise.all([jobsRequest, memoryRequest]).finally(() => setContextLoading(false))
  }, [])
  useEffect(() => { loadContext() }, [loadContext])
  async function createSession() {
    setBusy(true); setError('')
    try {
      const data = await terminal('/sessions/create', { method: 'POST', body: JSON.stringify({ agentName: agent }) })
      if (!data.sessionId) throw new Error('O serviço não retornou uma sessão válida.')
      setSessions(prev => [{ id: data.sessionId, name: data.session?.name || 'Nova conversa' }, ...prev]); setSession(data.sessionId); setApprovals(0)
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha ao criar sessão') } finally { setBusy(false) }
  }
  async function archiveSession() {
    if (!session) return
    setBusy(true)
    try {
      await terminal(`/sessions/${encodeURIComponent(session)}`, { method: 'PATCH', body: JSON.stringify({ archived: true }) })
      setSessions(prev => prev.map(s => s.id === session ? { ...s, archived: true } : s)); setSession(null); setApprovals(0)
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha ao encerrar') } finally { setBusy(false) }
  }
  async function readSource(source: Source) {
    const request = ++sourceRequest.current
    setSourcePath(source.path); setSourceText(''); setMemoryError('')
    try {
      const text = await api.getRaw(`/memory/${source.path.split('/').map(encodeURIComponent).join('/')}`)
      if (request === sourceRequest.current) setSourceText(text || 'Arquivo vazio.')
    } catch { if (request === sourceRequest.current) { setMemoryError('Não foi possível abrir esta fonte. Tente novamente.'); setSourceText('Conteúdo indisponível nesta tentativa.') } }
  }
  const current = sessions.find(s => s.id === session)
  const attention = jobs.filter(j => j.status === 'failed').length
  return <div className="omni">
    <header className="omni-top"><div><span className="omni-eyebrow">WORKSPACE DE AGENTES</span><h1>OmniNexus<span className="omni-preview">Prévia</span></h1><p>Uma conversa. Autoria clara. Trabalho acompanhável.</p></div><Link className="omni-link" to="/overview">Painel EvoNexus <ArrowUpRight size={16} aria-hidden="true" /></Link></header>
    <div className="omni-summary"><span><span className="omni-dot" /> APIs existentes · sem dados de demonstração</span><span><ShieldCheck size={16} aria-hidden="true" /> Aprovações no contexto da conversa</span></div>
    <a className="omni-mobile-jump" href="#omni-conversation">Ir à conversa ↓</a>
    <div className="omni-grid">
      <aside className="omni-panel omni-squad"><div className="omni-panel-title"><Layers3 size={18} aria-hidden="true" /><h2>Seu squad</h2></div><p className="omni-muted">Escolha quem responde. Trocar de agente não transfere o histórico.</p>
        <label htmlFor="omni-agent">Responsável pela conversa</label><select id="omni-agent" value={agent} disabled={loading || busy} onChange={e => { setSession(null); setSessions([]); setApprovals(0); setError(''); setAgent(e.target.value) }}><option value="">{loading ? 'Carregando squad…' : 'Selecione um agente'}</option>{agents.map(a => <option key={a.name} value={a.name}>{a.name}</option>)}</select>
        <p className="omni-agent-description">{agents.find(a => a.name === agent)?.description || 'Agentes disponíveis conforme o cadastro atual. A função de orquestrador depende da configuração do agente.'}</p>
        <button className="omni-primary" disabled={!agent || busy} onClick={createSession}><Plus size={18} aria-hidden="true" />{busy ? 'Aguarde…' : 'Nova sessão'}</button>
        <button className="omni-mobile-tools" aria-expanded={sessionToolsOpen} aria-controls="omni-session-tools" onClick={() => setSessionToolsOpen(open => !open)}>{sessionToolsOpen ? 'Recolher histórico e voz' : 'Histórico e voz'}</button>
        <div id="omni-session-tools" className={`omni-session-tools ${sessionToolsOpen ? 'is-open' : ''}`}><div className="omni-section-label">RETOMAR UMA CONVERSA</div><div className="omni-sessions">{sessions.length === 0 && <p className="omni-muted">Nenhuma sessão carregada para este agente.</p>}{sessions.map(s => <button key={s.id} className={`omni-session ${s.id === session ? 'is-selected' : ''}`} aria-pressed={s.id === session} disabled={busy} onClick={() => { setSession(s.id); setApprovals(0) }}><MessageSquare size={16} aria-hidden="true" /><span><strong>{s.name || s.id.slice(0, 12)}</strong><small>{s.archived ? 'Arquivada · abrir histórico' : s.preview || 'Abrir conversa'}</small></span></button>)}</div>
        <div className="omni-voice"><MicOff size={18} aria-hidden="true" /><div><strong>Voz em preparação</strong><p>Microfone desativado nesta central. Nenhum áudio é capturado ou enviado.</p></div></div></div>
      </aside>
      <section id="omni-conversation" className="omni-panel omni-conversation" aria-label="Conversa com o agente"><div className="omni-conversation-head"><div><span className="omni-eyebrow">AUTORIA DA RESPOSTA</span><h2><Bot size={20} aria-hidden="true" />{agent || 'Selecione seu agente'}</h2><p>{current ? `${current.name || 'Sessão selecionada'} · ${current.archived ? 'arquivada' : 'aberta'}` : 'Crie uma sessão ou retome um histórico'}</p></div>{session && !current?.archived && <button disabled={busy || current?.active} title={current?.active ? 'Aguarde o trabalho ativo terminar antes de arquivar' : 'Arquiva o histórico; não cancela jobs'} onClick={archiveSession}>Encerrar e arquivar</button>}</div>
        {error && <div role="alert" className="omni-error">{error}</div>}
        {session && agent && !current?.archived ? <div className="omni-chat"><AgentChat key={`${agent}:${session}`} agent={agent} sessionId={session} voiceEnabled={false} accentColor="#a3ff12" onPendingCountChange={(_, count) => setApprovals(count)} onTurnCompleted={loadContext} /></div> : <div className="omni-empty"><div className="omni-orbit"><MessageSquare size={30} aria-hidden="true" /></div><span className="omni-eyebrow">DO OBJETIVO À EXECUÇÃO</span><h2>{current?.archived ? 'Histórico preservado' : 'O que vamos construir hoje?'}</h2><p>{current?.archived ? 'Abra esta sessão na página do agente para consultar ou restaurar o histórico.' : 'Escolha um agente do squad e inicie uma sessão. Respostas, ferramentas e pedidos de aprovação aparecem aqui.'}</p>{current?.archived ? <Link className="omni-link" to={`/agents/${encodeURIComponent(agent)}`}>Abrir agente <ArrowUpRight size={16} /></Link> : <button className="omni-primary" disabled={!agent || busy} onClick={createSession}>Começar uma conversa <Plus size={18} aria-hidden="true" /></button>}<small>Uma nova sessão só é criada quando você solicita.</small></div>}
      </section>
      <aside className="omni-panel omni-context"><div className="omni-panel-title"><h2>Contexto de trabalho</h2><button aria-label="Atualizar jobs e fontes" disabled={contextLoading} onClick={() => { setContextLoading(true); loadContext() }}><RefreshCw size={16} /></button></div><div className="omni-tabs" role="group" aria-label="Contexto"><button aria-pressed={tab === 'jobs'} onClick={() => setTab('jobs')}>Atividade</button><button aria-pressed={tab === 'memory'} onClick={() => setTab('memory')}>Memória</button></div>
        {tab === 'jobs' ? <><div className="omni-approval" role="status"><ShieldCheck size={20} aria-hidden="true" /><div><strong>{approvals ? `${approvals} aprovação(ões) pendente(s)` : 'Você mantém o controle'}</strong><p>{approvals ? 'Revise a solicitação e autorize ou recuse na conversa.' : 'Solicitações recebidas nesta sessão aparecem na conversa.'}</p></div></div><div className="omni-section-label">JOBS DA OPERAÇÃO · TODOS OS AGENTES</div>{jobsError && <p role="status" className="omni-error">{jobsError}</p>}{contextLoading && <p role="status" className="omni-muted">Atualizando contexto…</p>}{!contextLoading && !jobsError && !jobs.length && <p className="omni-muted">Nenhum job retornado pela API.</p>}{attention > 0 && <p className="omni-warning">{attention} job(s) com falha precisam de atenção.</p>}<div className="omni-jobs">{jobs.slice(0, 8).map(j => <article className="omni-job" key={j.id}><div><span className={`omni-status status-${j.status}`}>{statusLabel[j.status] || j.status}</span><small>{j.agent}</small></div><h3>{j.prompt || j.id}</h3><p>Etapa: {j.stage || 'Não informada'}</p>{j.error && <p className="omni-warning">Bloqueio: {j.error}</p>}</article>)}</div><Link className="omni-link" to="/orquestracao">Ver jobs e detalhes <ArrowUpRight size={16} aria-hidden="true" /></Link></> : <><div className="omni-panel-title"><Brain size={20} aria-hidden="true" /><h3>Fontes de memória</h3></div><p className="omni-muted">Arquivos globais retornados pela API. Esta lista não comprova que foram usados na resposta.</p>{memoryError && <p role="status" className="omni-error">{memoryError}</p>}{contextLoading && <p role="status" className="omni-muted">Carregando fontes…</p>}{!contextLoading && !memoryError && !sources.length && <p className="omni-muted">Nenhuma fonte global retornada.</p>}{sources.map(s => <button className="omni-source" key={s.path} onClick={() => readSource(s)}><strong>{s.name}</strong><small>{s.path}</small></button>)}{sourcePath && <details open><summary>Fonte: {sourcePath}</summary><div className="omni-source-text"><Markdown>{sourceText || 'Carregando fonte…'}</Markdown></div></details>}<Link className="omni-link" to="/memory">Explorar memória por agente <ArrowUpRight size={16} aria-hidden="true" /></Link></>}
      </aside>
    </div><footer className="omni-footer"><span><CheckCircle2 size={14} aria-hidden="true" /> Este sistema utiliza EvoNexus · © 2026 Evolution Foundation</span><Link to="/settings">Configurações e administração</Link><a href="/docs">Documentação</a></footer>
  </div>
}
