import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Channel = { id: string; name: string; platform: string; provider: string }
type Target = { platform: string; integration_id: string; content: string; scheduled_at_utc: string; settings: Record<string, unknown> }
type Row = { platform: string; integration_id: string; content: string; localDate: string; provider?: string; settings?: Record<string, unknown> }
type Release = {
  revision: number; digest: string; approval_valid: boolean; approved_by: string | null; invalidated_reason: string | null; busy: boolean
  snapshot: { render_version: string; binding: { render_sha256: string }; channels: Target[] }
  progress: { channels?: Record<string, { state: string; post_id: string | null; remote_state?: string; release_url: string | null; error?: string }> }
}
type Job = { id: string; platform: string; caption: string | null; scheduled_at_utc: string | null }
const field = 'w-full rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#e6edf3] focus:outline-2 focus:outline-[#58a6ff]'
const button = 'min-h-11 rounded-lg border border-[#30363d] px-3 py-2 text-sm text-[#e6edf3] hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed'
const labels: Record<string, string> = { pending: 'Pendente', scheduled: 'Agendado confirmado', published: 'Publicado confirmado', unknown: 'Reconciliação necessária', remote_mismatch: 'Divergência no Postiz', remote_error: 'Falha no destino', retryable_failure: 'Pode retentar', awaiting_confirmation: 'Aguardando confirmação', creating_draft: 'Criação em andamento', draft_created: 'Draft criado', scheduling: 'Agendando', calendar_expired: 'Horário expirado' }
const localDate = (iso: string | null) => {
  if (!iso) return ''
  const date = new Date(iso)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

export default function MediaReleasePanel({ job, onChange }: { job: Job; onChange: () => void }) {
  const [release, setRelease] = useState<Release | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [rows, setRows] = useState<Row[]>([{ platform: job.platform, integration_id: '', content: job.caption || '', localDate: localDate(job.scheduled_at_utc) }])
  const [version, setVersion] = useState('v1')
  const [savedForm, setSavedForm] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const root = `/media/jobs/${job.id}/release`
  const dirty = JSON.stringify({ rows, version }) !== savedForm
  const lock = busy || loading || Boolean(release?.busy)
  const dispatched = Object.values(release?.progress.channels || {}).some(c => c.post_id || ['unknown', 'creating_draft'].includes(c.state))
  const editLock = lock || dispatched

  const accept = (data: Release) => {
    const next = data.snapshot.channels.map(c => ({ platform: c.platform, integration_id: c.integration_id, content: c.content, localDate: localDate(c.scheduled_at_utc), settings: c.settings }))
    setRelease(data); setRows(next); setVersion(data.snapshot.render_version)
    setSavedForm(JSON.stringify({ rows: next, version: data.snapshot.render_version }))
  }
  useEffect(() => {
    let active = true
    api.get(root).then(data => { if (active) accept(data) }).catch((e: Error) => {
      if (active && !e.message.startsWith('404')) setError('Falha ao carregar revisão. ' + e.message)
    }).finally(() => { if (active) setLoading(false) })
    api.get('/media/channels').then(data => { if (active) setChannels(data) }).catch((e: Error) => {
      if (active) setError('Falha ao listar contas conectadas. ' + e.message)
    })
    return () => { active = false }
  }, [root])
  const update = (index: number, patch: Partial<Row>) => { setRows(current => current.map((row, i) => i === index ? { ...row, ...patch } : row)); setNotice('') }
  const run = async (action: 'save' | 'approve' | 'distribute' | 'refresh') => {
    setBusy(true); setError(''); setNotice('')
    try {
      let data: Release
      if (action === 'save') {
        if (!version.trim() || rows.some(row => !row.integration_id || !row.content.trim() || !row.localDate)) throw new Error('Preencha versão, conta, copy e horário de cada canal.')
        data = await api.put(root, { render_version: version, expected_digest: release?.digest,
          channels: rows.map(row => ({ platform: row.platform, integration_id: row.integration_id, content: row.content,
            scheduled_at_utc: new Date(row.localDate).toISOString(), provider: row.provider, settings: row.settings })) })
      } else data = await api.post(`${root}/${action}`, action === 'approve' ? { digest: release?.digest } : undefined)
      accept(data); onChange()
      setNotice(action === 'save' ? 'Revisão salva. Confira o resumo antes de aprovar.' : action === 'approve' ? 'Aprovação registrada para esta revisão.' : 'Estados atualizados. Confira cada canal abaixo.')
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Falha na operação.'
      const known: Record<string, string> = {
        reconcile_existing_posts_before_replacing_release: 'Já há posts criados ou incertos. Confira os resultados e reconcilie antes de mudar conteúdo ou calendário.',
        approval_stale_or_account_unavailable: 'A aprovação está desatualizada ou uma conta ficou indisponível. Confira a revisão e as contas antes de continuar.',
        human_session_required: 'A aprovação precisa ser feita pela sessão humana autenticada.',
        release_busy: 'Há uma operação em andamento ou interrompida. Confira os checkpoints antes de retentar.',
        stale_release_revision: 'Esta revisão mudou. Recarregue os dados e confira o resumo novamente.',
      }
      setError(Object.entries(known).find(([key]) => message.includes(key))?.[1] || message)
      try { setRelease(await api.get(root)) } catch { /* preserve original error */ }
    } finally { setBusy(false) }
  }
  return <section aria-label="Revisão e distribuição" className="mb-5 space-y-4 rounded-xl border border-[#30363d] bg-[#0d1117] p-4">
    <h3 className="text-base font-semibold text-[#e6edf3]">Revisar e distribuir</h3>
    <p className="text-sm text-[#8b949e]">Confira o vídeo, as copies, as contas e os horários. Alterações exigem nova aprovação.</p>
    {error && <p role="alert" className="rounded-lg border border-[#f85149]/40 p-3 text-sm text-[#ff938a]">{error}</p>}
    {notice && <p role="status" className="text-sm text-[#00FFA7]">{notice}</p>}
    {release?.invalidated_reason && <p className="text-sm text-[#e3b341]">Aprovação pendente ou inválida: {release.invalidated_reason}</p>}
    {release?.busy && <p role="status" className="text-sm text-[#e3b341]">Operação em andamento ou interrompida. Recarregue os dados e confira os checkpoints antes de retentar.</p>}
    {dispatched && <p className="text-sm text-[#e3b341]">Já há posts criados ou incertos. Mudanças no conteúdo ou calendário exigem reconciliação dos resultados.</p>}
    <label className="block text-sm text-[#c9d1d9]">Versão do vídeo<input className={`${field} mt-1`} value={version} disabled={editLock} onChange={e => setVersion(e.target.value)} /></label>
    {rows.map((row, index) => <fieldset key={index} disabled={editLock} className="space-y-3 rounded-lg border border-[#30363d] p-3">
      <legend className="px-1 text-sm text-[#c9d1d9]">Canal {index + 1}</legend>
      <label className="block text-sm text-[#c9d1d9]">Conta conectada<select className={`${field} mt-1`} value={row.integration_id} onChange={e => {
        const selected = channels.find(channel => channel.id === e.target.value)
        if (selected) update(index, { integration_id: selected.id, platform: selected.platform, provider: selected.provider, settings: undefined })
      }}><option value="" disabled>Selecione uma conta</option>
        {row.integration_id && !channels.some(c => c.id === row.integration_id) && <option value={row.integration_id}>Conta indisponível — selecione outra</option>}
        {channels.map(channel => <option key={channel.id} value={channel.id}>{channel.name} · {channel.platform}</option>)}
      </select></label>
      <label className="block text-sm text-[#c9d1d9]">Copy desta rede<textarea rows={3} className={`${field} mt-1`} value={row.content} onChange={e => update(index, { content: e.target.value })} /></label>
      <label className="block text-sm text-[#c9d1d9]">Horário ({timezone})<input type="datetime-local" className={`${field} mt-1`} value={row.localDate} onChange={e => update(index, { localDate: e.target.value })} /></label>
      {rows.length > 1 && <button type="button" className={button} onClick={() => setRows(current => current.filter((_, i) => i !== index))}>Remover canal {index + 1}</button>}
    </fieldset>)}
    <div className="flex flex-wrap gap-2">
      <button type="button" disabled={editLock} className={button} onClick={() => setRows(current => [...current, { platform: '', integration_id: '', content: '', localDate: '' }])}>Adicionar outra rede</button>
      <button type="button" disabled={editLock || !dirty} className={button} onClick={() => run('save')}>{busy ? 'Processando…' : 'Salvar revisão para aprovação'}</button>
      {release && <button type="button" disabled={busy} className={button} onClick={() => {
        api.get(root).then(setRelease).catch((e: Error) => setError(e.message))
      }}>Recarregar revisão</button>}
    </div>
    {release && <div className="space-y-3 border-t border-[#30363d] pt-3">
      <h4 className="text-sm font-semibold text-[#e6edf3]">Revisão {release.revision} · {release.snapshot.render_version}</h4>
      <p className="break-all text-xs text-[#8b949e]">SHA-256 do vídeo: {release.snapshot.binding.render_sha256}</p>
      {release.snapshot.channels.map(channel => <div key={channel.integration_id} className="space-y-1 text-sm text-[#c9d1d9]">
        <p className="font-medium">{channels.find(c => c.id === channel.integration_id)?.name || channel.integration_id} · {channel.platform}</p>
        <p className="whitespace-pre-wrap break-words">{channel.content}</p>
        <p>{new Date(channel.scheduled_at_utc).toLocaleString()} ({timezone}) · {channel.scheduled_at_utc}</p>
        <details><summary className="cursor-pointer text-[#8b949e]">Opções de publicação</summary><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(channel.settings, null, 2)}</pre></details>
      </div>)}
      {dirty && <p className="text-sm text-[#e3b341]">Há alterações não salvas. Salve uma nova revisão antes de aprovar ou agendar.</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={lock || dirty || release.approval_valid} className={button} onClick={() => run('approve')}>Aprovar vídeo, copies e calendário</button>
        <button type="button" disabled={lock || dirty || !release.approval_valid} className={button} onClick={() => run('distribute')}>Agendar e distribuir nos canais aprovados</button>
        <button type="button" disabled={lock} className={button} onClick={() => run('refresh')}>Consultar resultados por canal</button>
      </div>
      {release.approval_valid && <p className="text-sm text-[#00FFA7]">Revisão aprovada por {release.approved_by}.</p>}
      {Object.entries(release.progress.channels || {}).map(([id, state]) => <div key={id} className="space-y-1 rounded-lg border border-[#30363d] p-3 text-sm text-[#c9d1d9]">
        <p className="font-medium">{channels.find(c => c.id === id)?.name || id}: {labels[state.state] || state.state}</p>
        {state.post_id && <p className="break-all text-xs text-[#8b949e]">Postiz: {state.post_id} · estado remoto: {state.remote_state || 'não confirmado'}</p>}
        {state.error && <p className="text-[#e3b341]">{state.error}</p>}
        {state.release_url && <a className="break-all text-[#58a6ff] underline" href={state.release_url} target="_blank" rel="noreferrer">Abrir publicação confirmada</a>}
      </div>)}
    </div>}
    <p className="text-xs text-[#8b949e]">Cancelar o job ou invalidar a aprovação não cancela posts já agendados no destino. Resultados incertos exigem reconciliação.</p>
  </section>
}
