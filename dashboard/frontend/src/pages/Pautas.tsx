import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Newspaper, Check, X, Pencil, Mic, Square, Loader2, RefreshCw,
  CheckCheck, TrendingUp,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

// Fila de pautas da esteira de conteúdo — até aqui só existia como API
// (`/api/pautas`), consumida pelo research semanal e pela rotina diária.
// O Felipe não tinha onde ver, editar ou dar feedback nela sem curl.

interface Pauta {
  id: number
  ciclo: string
  prioridade: number
  keyword: string
  titulo: string | null
  angulo: string | null
  volume: number | null
  kd: number | null
  data_alvo: string
  publish_at: string
  status: 'proposta' | 'aprovada' | 'escrita' | 'publicada' | 'descartada'
  ghost_post_id: string | null
  ghost_url: string | null
  motivo: string | null
  criado_em: string
  atualizado_em: string
}

const STATUS_COLOR: Record<string, string> = {
  proposta: '#8b949e',
  aprovada: '#58a6ff',
  escrita: '#d29922',
  publicada: '#00FFA7',
  descartada: '#f85149',
}

const STATUS_LABEL: Record<string, string> = {
  proposta: 'Proposta',
  aprovada: 'Aprovada',
  escrita: 'Escrita',
  publicada: 'Publicada',
  descartada: 'Descartada',
}

const API = import.meta.env.DEV ? 'http://localhost:8080' : ''

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status] || '#8b949e'
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full border whitespace-nowrap font-medium"
      style={{ color, borderColor: `${color}55`, background: `${color}14` }}
    >
      {STATUS_LABEL[status] || status}
    </span>
  )
}

function fmtData(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

function fmtHora(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

async function apiCall(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${API}/api${path}`, {
    credentials: 'include',
    headers: { 'X-Requested-With': 'XMLHttpRequest', ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (data?.error) msg = data.error
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

function KeywordEditor({ pauta, onSaved }: { pauta: Pauta; onSaved: (p: Pauta) => void }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(pauta.keyword)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const save = async () => {
    if (!value.trim() || value === pauta.keyword) { setEditing(false); return }
    setSaving(true)
    setErr(null)
    try {
      await apiCall(`/pautas/${pauta.id}/keyword`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: value.trim() }),
      })
      onSaved({
        ...pauta, keyword: value.trim(),
        status: pauta.status === 'aprovada' ? 'proposta' : pauta.status,
      })
      setEditing(false)
    } catch (e: any) {
      setErr(e?.message || 'falha ao salvar')
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="flex items-center gap-1.5 text-left group"
        title="Editar keyword"
      >
        <span className="text-sm text-gray-200">{pauta.keyword}</span>
        <Pencil size={12} className="text-gray-600 group-hover:text-gray-400 shrink-0" />
      </button>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
        className="bg-black/40 border border-white/15 rounded px-2 py-1 text-sm text-gray-100 w-full"
      />
      <button onClick={save} disabled={saving} className="text-green-400 shrink-0">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
      </button>
      <button onClick={() => setEditing(false)} className="text-gray-500 shrink-0"><X size={14} /></button>
      {err && <span className="text-xs text-red-400">{err}</span>}
    </div>
  )
}

function AudioFeedback({ pauta, onSaved }: { pauta: Pauta; onSaved: (p: Pauta) => void }) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const start = async () => {
    setErr(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setBusy(true)
        try {
          const fd = new FormData()
          fd.append('audio', blob, 'feedback.webm')
          const res = await fetch(`${API}/api/pautas/${pauta.id}/feedback-audio`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: fd,
          })
          if (!res.ok) {
            const data = await res.json().catch(() => ({}))
            throw new Error(data?.error || `${res.status} ${res.statusText}`)
          }
          const data = await res.json()
          onSaved({ ...pauta, motivo: data.motivo })
        } catch (e: any) {
          setErr(e?.message || 'falha ao transcrever')
        } finally {
          setBusy(false)
        }
      }
      rec.start()
      recorderRef.current = rec
      setRecording(true)
    } catch {
      setErr('microfone indisponível ou permissão negada')
    }
  }

  const stop = () => {
    recorderRef.current?.stop()
    setRecording(false)
  }

  return (
    <div className="flex items-center gap-2">
      {busy ? (
        <span className="flex items-center gap-1 text-xs text-gray-400"><Loader2 size={12} className="animate-spin" /> transcrevendo...</span>
      ) : recording ? (
        <button onClick={stop} className="flex items-center gap-1 text-xs text-red-400 border border-red-400/40 rounded-full px-2 py-0.5">
          <Square size={10} /> parar
        </button>
      ) : (
        <button onClick={start} className="flex items-center gap-1 text-xs text-gray-400 hover:text-white border border-white/15 rounded-full px-2 py-0.5">
          <Mic size={12} /> gravar feedback
        </button>
      )}
      {err && <span className="text-xs text-red-400">{err}</span>}
    </div>
  )
}

export default function Pautas() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('goals', 'manage')

  const [pautas, setPautas] = useState<Pauta[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    apiCall('/pautas?limit=200')
      .then((data) => setPautas(Array.isArray(data.pautas) ? data.pautas : []))
      .catch((e) => setError(e?.message || 'Falha ao carregar pautas'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const updateLocal = (p: Pauta) => setPautas((prev) => prev.map((x) => (x.id === p.id ? p : x)))

  const mudarStatus = async (pauta: Pauta, novo: Pauta['status']) => {
    setBusyId(pauta.id)
    try {
      await apiCall(`/pautas/${pauta.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: novo }),
      })
      updateLocal({ ...pauta, status: novo })
    } catch (e: any) {
      setError(e?.message || 'falha ao mudar status')
    } finally {
      setBusyId(null)
    }
  }

  const aprovarCiclo = async (ciclo: string) => {
    setBusyId(-1)
    try {
      await apiCall(`/pautas/ciclo/${ciclo}/aprovar`, { method: 'POST' })
      load()
    } catch (e: any) {
      setError(e?.message || 'falha ao aprovar ciclo')
    } finally {
      setBusyId(null)
    }
  }

  // Ciclos, ordenados; dentro de cada um, dias em ordem, e dentro do dia por prioridade.
  const porCiclo = new Map<string, Pauta[]>()
  for (const p of pautas) {
    if (!porCiclo.has(p.ciclo)) porCiclo.set(p.ciclo, [])
    porCiclo.get(p.ciclo)!.push(p)
  }
  const ciclos = [...porCiclo.keys()].sort()

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Newspaper className="text-[#00FFA7]" size={22} />
          <h1 className="text-xl font-bold text-white">Fila de Pautas</h1>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white border border-white/15 rounded-lg px-3 py-1.5"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Atualizar
        </button>
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {loading && pautas.length === 0 ? (
        <div className="flex items-center justify-center py-20 text-gray-500">
          <Loader2 className="animate-spin mr-2" size={18} /> carregando...
        </div>
      ) : pautas.length === 0 ? (
        <div className="text-center py-20 text-gray-500">Nenhuma pauta na fila.</div>
      ) : (
        ciclos.map((ciclo) => {
          const items = porCiclo.get(ciclo)!.sort((a, b) =>
            a.data_alvo === b.data_alvo ? a.prioridade - b.prioridade : a.data_alvo.localeCompare(b.data_alvo))
          const pendentes = items.filter((p) => p.status === 'proposta').length
          const porDia = new Map<string, Pauta[]>()
          for (const p of items) {
            if (!porDia.has(p.data_alvo)) porDia.set(p.data_alvo, [])
            porDia.get(p.data_alvo)!.push(p)
          }

          return (
            <div key={ciclo} className="mb-8">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-300">
                  Ciclo {ciclo} <span className="text-gray-600 font-normal">({items.length} pautas)</span>
                </h2>
                {canManage && pendentes > 0 && (
                  <button
                    onClick={() => aprovarCiclo(ciclo)}
                    disabled={busyId === -1}
                    className="flex items-center gap-1.5 text-xs text-[#00FFA7] border border-[#00FFA7]/40 rounded-full px-3 py-1 hover:bg-[#00FFA7]/10"
                  >
                    <CheckCheck size={13} /> Aprovar {pendentes} pendente{pendentes > 1 ? 's' : ''}
                  </button>
                )}
              </div>

              {[...porDia.entries()].map(([dia, ps]) => (
                <div key={dia} className="mb-3">
                  <div className="text-xs uppercase tracking-wider text-gray-500 mb-1.5 pl-1">
                    {fmtData(dia)}
                  </div>
                  <div className="space-y-1.5">
                    {ps.map((p) => (
                      <div
                        key={p.id}
                        className="bg-[#111111] border border-white/10 rounded-xl px-4 py-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <StatusBadge status={p.status} />
                              <span className="text-xs text-gray-600">{fmtHora(p.publish_at)}</span>
                              {p.volume != null && (
                                <span className="flex items-center gap-1 text-xs text-gray-500">
                                  <TrendingUp size={11} /> {p.volume.toLocaleString('pt-BR')}/mês
                                </span>
                              )}
                            </div>
                            <KeywordEditor pauta={p} onSaved={updateLocal} />
                            {p.titulo && <div className="text-xs text-gray-500 mt-0.5">{p.titulo}</div>}
                            {p.motivo && (
                              <div className="text-xs text-gray-400 italic mt-1.5 border-l-2 border-white/10 pl-2">
                                {p.motivo}
                              </div>
                            )}
                            {p.ghost_url && (
                              <a href={p.ghost_url} target="_blank" rel="noreferrer"
                                 className="text-xs text-blue-400 hover:underline mt-1 inline-block">
                                ver no Ghost →
                              </a>
                            )}
                          </div>

                          {canManage && (
                            <div className="flex flex-col items-end gap-2 shrink-0">
                              <div className="flex items-center gap-1.5">
                                {p.status === 'proposta' && (
                                  <>
                                    <button
                                      onClick={() => mudarStatus(p, 'aprovada')}
                                      disabled={busyId === p.id}
                                      className="flex items-center gap-1 text-xs text-green-400 border border-green-400/40 rounded-full px-2 py-0.5 hover:bg-green-400/10"
                                    >
                                      <Check size={12} /> aprovar
                                    </button>
                                    <button
                                      onClick={() => mudarStatus(p, 'descartada')}
                                      disabled={busyId === p.id}
                                      className="flex items-center gap-1 text-xs text-red-400 border border-red-400/40 rounded-full px-2 py-0.5 hover:bg-red-400/10"
                                    >
                                      <X size={12} /> descartar
                                    </button>
                                  </>
                                )}
                                {p.status === 'aprovada' && (
                                  <button
                                    onClick={() => mudarStatus(p, 'descartada')}
                                    disabled={busyId === p.id}
                                    className="flex items-center gap-1 text-xs text-red-400 border border-red-400/40 rounded-full px-2 py-0.5 hover:bg-red-400/10"
                                  >
                                    <X size={12} /> descartar
                                  </button>
                                )}
                              </div>
                              {['proposta', 'aprovada'].includes(p.status) && (
                                <AudioFeedback pauta={p} onSaved={updateLocal} />
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        })
      )}
    </div>
  )
}
