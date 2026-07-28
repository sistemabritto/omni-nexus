import { useEffect, useMemo, useState } from 'react'
import {
  Clock, Play, Loader2, CheckCircle2, XCircle, Activity, DollarSign,
  CalendarClock, RefreshCw,
} from 'lucide-react'
import { api } from '../lib/api'
import { useTranslation } from 'react-i18next'

/**
 * Rotinas — o que roda sozinho, quando roda e quanto custa.
 *
 * Esta página juntou duas telas que se contradiziam. `/routines` listava
 * execuções passadas e `/scheduler` listava agendamentos, sem chave em comum:
 * a mesma rotina aparecia nas duas com nomes diferentes, e nenhuma das duas
 * respondia a pergunta real — "isso vai rodar de novo quando, e vai me custar
 * quanto?".
 *
 * Três decisões que valem para quem for mexer:
 *
 * 1. **Uma linha por rotina**, casada pelo script. Rotina agendada que nunca
 *    rodou aparece; execução histórica de rotina que saiu do agendador também.
 *    São estados diferentes e a tela diz qual é qual, em vez de somar tudo.
 * 2. **O motor é a informação cara.** 🐍 é Python determinístico e custa CPU;
 *    🤖 chama modelo e custa dinheiro toda vez. É o que decide se uma rotina
 *    pode rodar de 15 em 15 minutos.
 * 3. **Cartão no celular, tabela no desktop.** Onze colunas num telefone não
 *    viram tabela rolável, viram texto ilegível. O corte é `md`.
 */

interface Rotina {
  id: string
  nome: string
  script: string
  motor: 'python' | 'modelo' | ''
  agente: string
  agendamento: string
  proxima: string
  execucoes: number
  sucessoPct: number
  tempoMedio: string
  tokens: number
  custoTotal: number
  ultimaExecucao: string
  saude: 'ok' | 'atencao' | 'falha' | 'nova'
}

interface TarefaAgendada {
  name: string
  script: string
  schedule: string
  next_run?: string
  agent?: string
  engine?: string
}

/** Chave de casamento entre agendamento e histórico. */
function chaveDe(script: string, nome: string): string {
  const base = (script || '').replace('custom/', '').replace('.py', '')
  if (base) return base.replace(/_/g, '-')
  return (nome || '').toLowerCase().replace(/\s+/g, '-')
}

function tempoRelativo(iso: string): string {
  if (!iso || iso === '-') return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  const min = Math.floor((Date.now() - d.getTime()) / 60000)
  if (min < 1) return 'agora'
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `há ${h}h`
  const dias = Math.floor(h / 24)
  if (dias < 7) return `há ${dias}d`
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

/** Quando roda de novo. Vazio quando a rotina não está agendada. */
function proximaEm(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const min = Math.round((d.getTime() - Date.now()) / 60000)
  if (min <= 0) return 'agora'
  if (min < 60) return `em ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `em ${h}h`
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }) +
    ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

const MOTOR = {
  python: {
    emoji: '🐍',
    rotulo: 'Python',
    ajuda: 'Código determinístico. Não chama modelo, não gasta token.',
    cor: '#60A5FA',
  },
  modelo: {
    emoji: '🤖',
    rotulo: 'Modelo',
    ajuda: 'Chama um modelo de linguagem. Custa dinheiro a cada execução.',
    cor: '#FBBF24',
  },
} as const

function SeloMotor({ motor }: { motor: Rotina['motor'] }) {
  if (!motor) return <span className="text-[#3F3F46] text-xs">—</span>
  const m = MOTOR[motor]
  return (
    <span
      title={m.ajuda}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border whitespace-nowrap"
      style={{ backgroundColor: `${m.cor}14`, color: m.cor, borderColor: `${m.cor}33` }}
    >
      <span aria-hidden>{m.emoji}</span> {m.rotulo}
    </span>
  )
}

function combinar(metricas: any, agendadas: TarefaAgendada[]): Rotina[] {
  const dados = metricas?.metrics || {}
  const porChave = new Map<string, Rotina>()

  for (const [id, m] of Object.entries<any>(dados)) {
    const script = m.script || ''
    const execucoes = Number(m.runs || 0)
    const sucessos = Number(m.successes || 0)
    // Derivado das contagens cruas, nunca do `success_rate` gravado: uma
    // rotina já escreveu esse campo como fração 0-1 e a tela mostrou "0,83%".
    const pct = execucoes > 0 ? Math.round((sucessos / execucoes) * 100) : 0
    const ultimoOk = typeof m.last_success === 'boolean' ? m.last_success : null
    const segundos = Number(m.avg_seconds || 0)
    porChave.set(chaveDe(script, id), {
      id,
      nome: m.name || id.replace(/-/g, ' ').replace(/^\w/, (c: string) => c.toUpperCase()),
      script,
      motor: (m.engine || '') as Rotina['motor'],
      agente: m.agent && m.agent !== 'none' ? m.agent : '',
      agendamento: '',
      proxima: '',
      execucoes,
      sucessoPct: pct,
      tempoMedio: segundos > 0 ? `${segundos.toFixed(1)}s` : '—',
      tokens: Number(m.total_input_tokens || 0) + Number(m.total_output_tokens || 0),
      custoTotal: Number(m.total_cost_usd || 0),
      ultimaExecucao: m.last_run || '',
      saude: execucoes === 0 ? 'nova'
        : ultimoOk === false ? 'falha'
        : pct >= 90 ? 'ok' : pct >= 70 ? 'atencao' : 'falha',
    })
  }

  for (const t of agendadas) {
    const chave = chaveDe(t.script, t.name)
    const existente = porChave.get(chave)
    if (existente) {
      existente.agendamento = t.schedule || ''
      existente.proxima = t.next_run || ''
      // O nome do agendador é o que o humano escreveu; o do metrics é derivado
      // do arquivo. Entre "Good Morning" e "good-morning", o primeiro ganha.
      if (t.name) existente.nome = t.name
      if (!existente.motor && t.engine) existente.motor = t.engine as Rotina['motor']
      if (!existente.agente && t.agent) existente.agente = t.agent
      continue
    }
    porChave.set(chave, {
      id: chave, nome: t.name || chave, script: t.script || '',
      motor: (t.engine || '') as Rotina['motor'], agente: t.agent || '',
      agendamento: t.schedule || '', proxima: t.next_run || '',
      execucoes: 0, sucessoPct: 0, tempoMedio: '—', tokens: 0, custoTotal: 0,
      ultimaExecucao: '', saude: 'nova',
    })
  }

  return [...porChave.values()]
}

const SAUDE = {
  ok: { cor: '#00FFA7', rotulo: 'saudável' },
  atencao: { cor: '#FBBF24', rotulo: 'atenção' },
  falha: { cor: '#EF4444', rotulo: 'falhando' },
  nova: { cor: '#667085', rotulo: 'sem histórico' },
} as const

function Cartao({ label, valor, icone: Icone }: { label: string; valor: string | number; icone: any }) {
  return (
    <div className="bg-[#161b22] border border-[#21262d] rounded-2xl p-4 sm:p-5">
      <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-[#00FFA7]/8 border border-[#00FFA7]/15 mb-3">
        <Icone size={18} className="text-[#00FFA7]" />
      </div>
      <p className="text-2xl sm:text-3xl font-bold text-[#e6edf3] tracking-tight tabular-nums">{valor}</p>
      <p className="text-sm text-[#667085] mt-1">{label}</p>
    </div>
  )
}

type Filtro = 'agendadas' | 'todas'

export default function Routines() {
  const { t } = useTranslation()
  const [rotinas, setRotinas] = useState<Rotina[]>([])
  const [carregando, setCarregando] = useState(true)
  const [filtro, setFiltro] = useState<Filtro>('agendadas')
  const [execucao, setExecucao] = useState<Record<string, 'idle' | 'running' | 'success' | 'error'>>({})

  const carregar = () => {
    setCarregando(true)
    Promise.all([
      api.get('/routines').catch(() => ({ metrics: {} })),
      api.get('/scheduler').catch(() => []),
    ])
      .then(([m, s]) => setRotinas(combinar(m, Array.isArray(s) ? s : [])))
      .catch(() => setRotinas([]))
      .finally(() => setCarregando(false))
  }

  useEffect(carregar, [])

  const visiveis = useMemo(() => {
    const lista = filtro === 'agendadas'
      ? rotinas.filter((r) => r.agendamento)
      : rotinas
    // Agendadas primeiro, pela próxima execução; depois as demais, pela última.
    return [...lista].sort((a, b) => {
      if (!!a.proxima !== !!b.proxima) return a.proxima ? -1 : 1
      if (a.proxima && b.proxima) return a.proxima.localeCompare(b.proxima)
      return (b.ultimaExecucao || '').localeCompare(a.ultimaExecucao || '')
    })
  }, [rotinas, filtro])

  const totais = useMemo(() => visiveis.reduce(
    (acc, r) => ({
      execucoes: acc.execucoes + r.execucoes,
      custo: acc.custo + r.custoTotal,
      comModelo: acc.comModelo + (r.motor === 'modelo' ? 1 : 0),
    }),
    { execucoes: 0, custo: 0, comModelo: 0 },
  ), [visiveis])

  const disparar = async (r: Rotina) => {
    setExecucao((p) => ({ ...p, [r.id]: 'running' }))
    try {
      await api.post(`/routines/${r.id}/run`)
      setExecucao((p) => ({ ...p, [r.id]: 'success' }))
    } catch {
      setExecucao((p) => ({ ...p, [r.id]: 'error' }))
    }
    setTimeout(() => setExecucao((p) => ({ ...p, [r.id]: 'idle' })), 5000)
  }

  const BotaoRodar = ({ r }: { r: Rotina }) => {
    const estado = execucao[r.id] || 'idle'
    if (estado === 'running') return (
      <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-[#FBBF24]/10 text-[#FBBF24] border border-[#FBBF24]/20">
        <Loader2 size={10} className="animate-spin" /> rodando
      </span>
    )
    if (estado === 'success') return (
      <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20">
        <CheckCircle2 size={10} /> disparada
      </span>
    )
    if (estado === 'error') return (
      <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
        <XCircle size={10} /> falhou
      </span>
    )
    return (
      <button
        onClick={() => disparar(r)}
        className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-[#00FFA7]/10 text-[#00FFA7] border border-[#00FFA7]/20 hover:bg-[#00FFA7]/20 transition-colors"
        title={`Rodar ${r.nome} agora`}
      >
        <Play size={10} /> rodar
      </button>
    )
  }

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#e6edf3] tracking-tight">{t('routines.title')}</h1>
          <p className="text-[#667085] text-sm mt-1">
            O que roda sozinho, quando roda de novo e quanto custa
          </p>
        </div>
        <button
          onClick={carregar}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[#21262d] bg-[#161b22] text-[#667085] hover:text-[#00FFA7] hover:border-[#00FFA7]/30 transition-colors text-sm"
        >
          <RefreshCw size={15} className={carregando ? 'animate-spin' : ''} /> Atualizar
        </button>
      </div>

      {/* Legenda do motor — a distinção que a página existe para deixar clara */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-6 text-xs text-[#667085]">
        <span className="flex items-center gap-1.5">
          <span aria-hidden>🐍</span> <strong className="text-[#60A5FA] font-medium">Python</strong>
          — determinística, não gasta token
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden>🤖</span> <strong className="text-[#FBBF24] font-medium">Modelo</strong>
          — chama uma LLM, custa por execução
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
        <Cartao label="Rotinas" valor={visiveis.length} icone={Clock} />
        <Cartao label="Chamam modelo" valor={totais.comModelo} icone={Activity} />
        <Cartao label="Execuções" valor={totais.execucoes.toLocaleString('pt-BR')} icone={CalendarClock} />
        <Cartao label="Custo acumulado" valor={`US$ ${totais.custo.toFixed(2)}`} icone={DollarSign} />
      </div>

      <div className="flex items-center gap-2 mb-4">
        {([['agendadas', 'Agendadas'], ['todas', 'Todas']] as const).map(([chave, rotulo]) => (
          <button
            key={chave}
            onClick={() => setFiltro(chave)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              filtro === chave
                ? 'bg-[#00FFA7]/10 text-[#00FFA7] border-[#00FFA7]/25'
                : 'bg-[#161b22] text-[#667085] border-[#21262d] hover:text-[#e6edf3]'
            }`}
          >
            {rotulo}
            {chave === 'todas' && (
              <span className="ml-1.5 opacity-60">{rotinas.length}</span>
            )}
          </button>
        ))}
        {filtro === 'todas' && (
          <span className="text-[11px] text-[#667085]">
            inclui histórico de rotinas que saíram do agendador
          </span>
        )}
      </div>

      {carregando ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-16 rounded-xl" />)}
        </div>
      ) : visiveis.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#161b22] border border-[#21262d]">
            <Clock size={32} className="text-[#3F3F46]" />
          </div>
          <p className="text-[#667085]">Nenhuma rotina agendada</p>
        </div>
      ) : (
        <>
          {/* Celular: um cartão por rotina. Tabela de 9 colunas num telefone
              não rola, só encolhe até ninguém conseguir ler. */}
          <div className="md:hidden space-y-3">
            {visiveis.map((r) => (
              <div key={r.id} className="bg-[#161b22] border border-[#21262d] rounded-xl p-4">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0">
                    <p className="text-[#e6edf3] font-medium text-sm truncate">{r.nome}</p>
                    <p className="text-[11px] text-[#667085] font-mono truncate">{r.script || '—'}</p>
                  </div>
                  <SeloMotor motor={r.motor} />
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#667085] mb-3">
                  {r.agendamento && (
                    <span className="text-[#D0D5DD]">{r.agendamento}</span>
                  )}
                  {r.proxima && <span>· {proximaEm(r.proxima)}</span>}
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs mb-3">
                  <div>
                    <p className="text-[#667085]">execuções</p>
                    <p className="text-[#D0D5DD] tabular-nums">{r.execucoes}</p>
                  </div>
                  <div>
                    <p className="text-[#667085]">sucesso</p>
                    <p className="tabular-nums" style={{ color: SAUDE[r.saude].cor }}>
                      {r.execucoes ? `${r.sucessoPct}%` : '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-[#667085]">custo</p>
                    <p className="text-[#D0D5DD] tabular-nums">
                      {r.custoTotal > 0 ? `US$ ${r.custoTotal.toFixed(2)}` : '—'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-[#667085]">
                    {r.ultimaExecucao ? `última ${tempoRelativo(r.ultimaExecucao)}` : 'nunca rodou'}
                  </span>
                  <BotaoRodar r={r} />
                </div>
              </div>
            ))}
          </div>

          {/* Desktop */}
          <div className="hidden md:block bg-[#161b22] border border-[#21262d] rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[860px]">
                <thead>
                  <tr className="text-[#667085] text-[11px] uppercase tracking-wider bg-[#0d1117]/50 border-b border-[#21262d]">
                    <th className="text-left p-4 font-medium">Rotina</th>
                    <th className="text-left p-4 font-medium">Motor</th>
                    <th className="text-left p-4 font-medium">Quando</th>
                    <th className="text-left p-4 font-medium">Próxima</th>
                    <th className="text-right p-4 font-medium">Exec.</th>
                    <th className="text-right p-4 font-medium">Sucesso</th>
                    <th className="text-right p-4 font-medium">Custo</th>
                    <th className="text-right p-4 font-medium">Última</th>
                    <th className="text-right p-4 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {visiveis.map((r) => (
                    <tr key={r.id} className="border-t border-[#21262d]/60 hover:bg-white/[0.02] transition-colors">
                      <td className="p-4">
                        <p className="text-[#e6edf3] font-medium text-[13px]">{r.nome}</p>
                        <p className="text-[11px] text-[#667085] font-mono">{r.script || '—'}</p>
                      </td>
                      <td className="p-4"><SeloMotor motor={r.motor} /></td>
                      <td className="p-4 text-[#D0D5DD] text-[13px] whitespace-nowrap">
                        {r.agendamento || <span className="text-[#3F3F46]">não agendada</span>}
                      </td>
                      <td className="p-4 text-[#667085] text-[13px] whitespace-nowrap">
                        {proximaEm(r.proxima) || '—'}
                      </td>
                      <td className="p-4 text-right text-[#D0D5DD] tabular-nums text-[13px]">{r.execucoes}</td>
                      <td className="p-4 text-right tabular-nums text-[13px]" style={{ color: SAUDE[r.saude].cor }}>
                        {r.execucoes ? `${r.sucessoPct}%` : SAUDE.nova.rotulo}
                      </td>
                      <td className="p-4 text-right text-[#D0D5DD] tabular-nums text-[13px]">
                        {r.custoTotal > 0 ? `US$ ${r.custoTotal.toFixed(2)}` : '—'}
                      </td>
                      <td className="p-4 text-right text-[#667085] text-[13px] whitespace-nowrap">
                        {r.ultimaExecucao ? tempoRelativo(r.ultimaExecucao) : 'nunca'}
                      </td>
                      <td className="p-4 text-right"><BotaoRodar r={r} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
