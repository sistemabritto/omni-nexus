import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useCompanies } from '../context/CompanyContext'
import { useAuth } from '../context/AuthContext'
import MediaReleasePanel from './MediaReleasePanel'
import VideoProjectEditor from './VideoProjectEditor'
import CreativeReviewPanel from './CreativeReviewPanel'

type Upload = { id: string; batch: number; client_key: string; position: number; name: string; kind: string; status: string; received: number; declared_size: number; duplicate_of: string | null }
type Range = { start_seconds: number; end_seconds: number | null }
type Trim = Range | { keep_segments: Range[] }
const ranges = (trim?: Trim): Range[] => trim ? ('keep_segments' in trim ? trim.keep_segments : [trim]) : [{ start_seconds: 0, end_seconds: null }]
type Version = { creative_review: { eligible: boolean; reviewer: string; payload: unknown } | null; rejection: { reason: string; by: string; at: string } | null; snapshot: { production?: { entry_modes: string[]; script: string }; assets: { id: string; trim?: Trim }[] }; id: string; number: number; batch: number; script_revision: number; qa_valid: boolean; job: { id: string; status: string; render_sha256: string | null; platform: string; caption: string | null; scheduled_at_utc: string | null; last_error: string | null }; release: { progress: { channels?: Record<string, { state: string; error?: string }> } } | null }
type Source = { id: string; title: string; script: string; references: Ref[] }
type Ref = { label: string; reference: string }
type Recording = { version_count?: number; id: string; company_id: number; title: string; origin_type: string; origin_id: string; script_revision: number; batch: number; closed: boolean; revision: number; state: string; uploads: Upload[]; versions: Version[]; scripts: { number: number; text: string; references: Ref[] }[]; feedback: { id: string; version_id: string; text: string; audio_url: string | null; created_at: string }[] }
const base = import.meta.env.DEV ? 'http://localhost:8080' : ''
const field = 'w-full rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-3 text-base text-[#e6edf3]'
const button = 'min-h-11 rounded-lg border border-[#30363d] px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed'
const box = 'rounded-xl border border-[#30363d] bg-[#161b22] p-4 space-y-4'
const states: Record<string, string> = { changes_requested: 'Ajustes solicitados', ready_to_record: 'Pronto para gravar', receiving_raw: 'Recebendo brutos', ready_to_edit: 'Pronto para editar', editing: 'Editando', editing_attention: 'Edição precisa de atenção', in_review: 'Em revisão', approved: 'Aprovado', scheduled: 'Agendado confirmado', published: 'Publicado confirmado', partial_distribution: 'Distribuição parcial', distribution_attention: 'Conferir distribuição' }
const qaLabels: Record<string, string> = { audio: 'Ouvi todo o áudio e conferi sincronismo', captions: 'Conferi as legendas (ou a ausência intencional)', face: 'Conferi rosto e enquadramento', safe_zones: 'Conferi textos e áreas seguras', rights: 'Tenho autorização de uso de todos os materiais' }
async function binary(path: string, method: string, data: BodyInit) {
  const response = await fetch(`${base}/api${path}`, { method, credentials: 'include', headers: { 'X-Requested-With': 'XMLHttpRequest' }, body: data })
  if (!response.ok) throw new Error(`${response.status}: ${(await response.json().catch(() => ({}))).error || 'Falha no envio'}`)
  return response.json()
}
const message = (e: unknown) => {
  const raw = e instanceof Error ? e.message : 'Falha na operação'
  if (raw.includes('checksum_mismatch') || raw.includes('chunk_corrupted')) return 'O arquivo não passou na conferência de integridade. Selecione o original novamente.'
  if (raw.includes('invalid_media_signature') || raw.includes('unsupported_media')) return 'Formato não reconhecido. Envie vídeo, foto ou áudio nos formatos aceitos.'
  if (raw.includes('independent_reviewer_required')) return 'A revisão criativa precisa ser registrada por outra conta autorizada, diferente de quem criou o projeto.'
  if (raw.includes('render_bound_creative_review_required')) return 'Registre uma revisão criativa elegível desta versão antes da conferência final.'
  if (raw.includes('creative_evidence_stale')) return 'As evidências desta revisão mudaram. Confira o render e registre a revisão novamente.'
  if (raw.includes('stickman_scene_required')) return 'Inclua uma cena de boneco palito para usar essa entrada.'
  if (raw.includes('long_cuts_footage_required')) return 'Inclua um vídeo de origem e a evidência da seleção editorial para usar cortes de longo.'
  if (raw.includes('enriched_edit_material_required')) return 'Selecione material enviado para a edição enriquecida.'
  if (raw.includes('generated_scene_required')) return 'Inclua cenas de motion, imagem ou stickman para o formato sem footage.'
  if (raw.includes('distribution_started_review_remote_posts')) return 'Esta versão já tem envio ao destino. Revise os posts no destino; reprovar aqui não cancela esse envio.'
  if (raw.includes('version_rejected_create_new_preview')) return 'Esta prévia foi reprovada. Reabra a edição e gere outra versão para conferir e aprovar.'
  if (raw.startsWith('413')) return 'O arquivo ou trecho enviado excedeu o limite permitido.'
  if (raw.startsWith('403') || raw.startsWith('404')) return 'Sem acesso a esta gravação/empresa. Peça ao administrador a liberação.'
  if (raw.startsWith('409')) return 'A gravação mudou ou há um envio incompleto. Atualize e confira os arquivos antes de tentar novamente.'
  return raw
}

export default function RecordingsQueue() {
  const { activeCompanyId } = useCompanies()
  return <CompanyRecordingsQueue key={activeCompanyId || 'none'} />
}

function CompanyRecordingsQueue() {
  const { activeCompanyId, activeCompany } = useCompanies()
  const { user } = useAuth()
  const [rows, setRows] = useState<Recording[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [recording, setRecording] = useState<Recording | null>(null)
  const [versionId, setVersionId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [script, setScript] = useState('')
  const [origin, setOrigin] = useState('')
  const [refs, setRefs] = useState<Ref[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [excludedSelection, setExcludedSelection] = useState<string[]>([])
  const chosen = recording?.uploads.filter(u => u.status === 'complete' && !excludedSelection.includes(u.id)).map(u => u.id) || []
  const [photoSeconds, setPhotoSeconds] = useState(3)
  const [trimInputs, setTrimInputs] = useState<Record<string, { start: string; end: string }[]>>({})
  const lastAssets = recording?.versions[0]?.snapshot.assets || []
  const trimInput = (id: string) => {
    const previous = lastAssets.find(asset => asset.id === id)?.trim
    return trimInputs[id] || ranges(previous).map(part => ({ start: String(part?.start_seconds ?? 0), end: part?.end_seconds == null ? '' : String(part.end_seconds) }))
  }
  const selectedCuts = (recording?.uploads || []).filter(upload => upload.kind === 'video' && chosen.includes(upload.id)).map(upload => ({
    id: upload.id, segments: trimInput(upload.id).map(input => ({ start_seconds: Number(input.start), end_seconds: input.end === '' ? null : Number(input.end) }))
  }))
  const cuts = Object.fromEntries(selectedCuts.map(({ id, segments }) => [id, segments.length === 1 ? segments[0] : { keep_segments: segments }]))
  const invalidCuts = selectedCuts.some(({ segments }) => segments.some((cut, index) => !Number.isFinite(cut.start_seconds) || cut.start_seconds < 0 ||
    (cut.end_seconds !== null && (!Number.isFinite(cut.end_seconds) || cut.end_seconds <= cut.start_seconds)) ||
    (index > 0 && (segments[index - 1].end_seconds === null || cut.start_seconds < segments[index - 1].end_seconds!))))
  const [rejectionReason, setRejectionReason] = useState('')
  const [progress, setProgress] = useState('')
  const [feedback, setFeedback] = useState('')
  const [audio, setAudio] = useState<File | null>(null)
  const [capturing, setCapturing] = useState(false)
  const [checks, setChecks] = useState<Record<string, boolean>>({})
  const creationKey = useRef('')
  const feedbackKey = useRef<string | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const scope = useRef(activeCompanyId)
  const selectedRef = useRef(selected)
  useLayoutEffect(() => { scope.current = activeCompanyId; selectedRef.current = selected }, [activeCompanyId, selected])
  const root = recording ? `/recordings/${recording.id}` : ''
  const accept = useCallback((next: Recording) => {
    if (scope.current !== next.company_id || selectedRef.current !== next.id) return
    setRecording(next)
    setRows(current => current.map(row => row.id === next.id ? next : row))
  }, [])
  const reload = useCallback(async () => {
    if (!selected) return
    const result = await api.get(`/recordings/${selected}`)
    accept(result)
  }, [selected, accept])
  useEffect(() => {
    if (!activeCompanyId) return
    let alive = true
    api.get(`/recordings?company_id=${activeCompanyId}&summary=true`).then(data => { if (alive) setRows(data) }).catch(e => { if (alive) setError(message(e)) }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [activeCompanyId])
  useEffect(() => {
    if (!selected) return
    let alive = true
    api.get(`/recordings/${selected}`).then(data => { if (alive) accept(data) }).catch(e => { if (alive) setError(message(e)) }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [selected, accept])
  const select = (id: string | null) => {
    feedbackKey.current = null; setVersionId(''); setChecks({}); setFeedback(''); setAudio(null); setExcludedSelection([]); setTrimInputs({}); setRejectionReason(''); setError(''); setRecording(null); setLoading(Boolean(id))
    if (recorder.current?.state === 'recording') recorder.current.stop()
    stream.current?.getTracks().forEach(track => track.stop()); setCapturing(false); setSelected(id)
  }
  useEffect(() => {
    if (!recording?.closed || !recording.versions.some(v => ['queued', 'preparing', 'generating', 'rendering', 'validating'].includes(v.job.status))) return
    const timer = setInterval(() => { reload().catch(e => setError(message(e))) }, 5000)
    return () => clearInterval(timer)
  }, [recording, reload])
  useEffect(() => () => { scope.current = null; selectedRef.current = null; if (recorder.current?.state === 'recording') recorder.current.stop(); stream.current?.getTracks().forEach(track => track.stop()) }, [])
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  const version = recording?.versions.find(v => v.id === versionId) || recording?.versions[0]
  const current = Boolean(recording?.closed && version && version.id === recording.versions[0]?.id && version.batch === recording.batch && version.script_revision === recording.script_revision)
  const ready = Boolean(version && (['ready_for_review', 'approved'].includes(version.job.status) || version.rejection) && version.job.render_sha256)
  const uploadFiles = async (files: File[]) => {
    if (!recording) return
    const recId = recording.id; const companyId = recording.company_id; const path = `/recordings/${recId}`
    const pending: { file: File; upload: Upload }[] = []
    let position = Math.max(-1, ...recording.uploads.map(u => u.position)) + 1
    // Reserve every selected file before sending bytes: closing cannot race the first upload.
    for (const file of files) {
      if (scope.current !== companyId || selectedRef.current !== recId) throw new Error('Empresa alterada. Retome o envio na gravação original.')
      const key = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${file.name}:${file.size}:${file.lastModified}`)))).map(b => b.toString(16).padStart(2, '0')).join('')
      const old = recording.uploads.find(u => u.batch === recording.batch && u.client_key === key)
      const upload: Upload = await api.post(`${path}/uploads`, { name: file.name, size: file.size, mime: file.type, client_key: key, position: old?.position ?? position++ })
      if (upload.status === 'excluded') throw new Error('Este envio foi excluído do lote. Reabra um novo lote para reenviar o arquivo.')
      pending.push({ file, upload })
    }
    for (const { file, upload } of pending) {
      for (let offset = 0; offset < file.size; offset += 4 * 1024 * 1024) {
        if (scope.current !== companyId || selectedRef.current !== recId) throw new Error('Envio pausado. Selecione os mesmos arquivos na gravação original para retomar.')
        await binary(`${path}/uploads/${upload.id}?offset=${offset}`, 'PUT', file.slice(offset, offset + 4 * 1024 * 1024))
        setProgress(`${file.name}: ${Math.min(100, Math.round((offset + 4 * 1024 * 1024) / file.size * 100))}%`)
      }
      await api.post(`${path}/uploads/${upload.id}/complete`)
    }
    setProgress('Envio concluído. Confira a ordem e feche o lote quando tudo estiver aqui.')
    await reload()
  }
  const move = async (index: number, delta: number) => {
    if (!recording) return
    const ids = recording.uploads.map(u => u.id); [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]]
    accept(await api.put(`${root}/order`, { expected_revision: recording.revision, upload_ids: ids }))
  }
  const capture = async () => {
    if (capturing) { recorder.current?.stop(); return }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Gravação de áudio indisponível. Anexe um arquivo de áudio abaixo.')
    const media = await navigator.mediaDevices.getUserMedia({ audio: true }); stream.current = media
    try {
      const instance = new MediaRecorder(media); recorder.current = instance
      const parts: BlobPart[] = []; instance.ondataavailable = event => { if (event.data.size) parts.push(event.data) }
      const recId = selectedRef.current
      instance.onstop = () => {
        if (selectedRef.current === recId) {
          const mime = instance.mimeType || 'audio/webm'
          setAudio(new File(parts, `feedback.${mime.includes('mp4') ? 'm4a' : mime.includes('ogg') ? 'ogg' : 'webm'}`, { type: mime })); setCapturing(false)
        }
        media.getTracks().forEach(track => track.stop()); recorder.current = null
      }
      instance.start(); setCapturing(true)
    } catch (e) { media.getTracks().forEach(track => track.stop()); throw e }
  }
  if (!activeCompanyId) return <p className={box}>Selecione uma empresa no perfil para abrir Gravações.</p>
  return <div className="space-y-4 text-[#e6edf3]">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Gravações e projetos</h2><p className="text-sm text-[#8b949e]">{activeCompany?.name} · roteiro, cenas, brutos e revisões no mesmo lugar</p></div><button className={button} disabled={busy} onClick={() => { creationKey.current = crypto.randomUUID(); setCreating(true); setTitle(''); setScript(''); setOrigin(''); setRefs([]) }}>Novo projeto de vídeo</button></div>
    {error && <p role="alert" className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm">{error} {progress && 'Se o envio foi interrompido, selecione os mesmos arquivos para retomar.'}</p>}
    {notice && <p role="status" className="p-3 text-sm text-green-300">{notice}</p>}
    {loading && <p role="status">Carregando…</p>}
    {creating && <form className={box} onSubmit={e => { e.preventDefault(); void run(async () => {
      const next: Recording = await api.post('/recordings', { company_id: activeCompanyId, title, script, origin_type: origin ? 'reel' : 'manual', origin_id: origin || creationKey.current, references: refs })
      if (scope.current !== next.company_id) return
      setRows(old => [next, ...old.filter(r => r.id !== next.id)]); select(next.id); setCreating(false)
    }) }}>
      <h3 className="font-semibold">Um projeto por roteiro</h3>
      {user?.role === 'admin' && <><button type="button" className={button} onClick={() => void run(async () => setSources(await api.get(`/recordings/reel-sources?company_id=${activeCompanyId}`)))}>Consultar Reels existentes</button>{sources.length > 0 && <label className="block">Origem existente<select className={field} value={origin} onChange={e => { const source = sources.find(s => String(s.id) === e.target.value); setOrigin(e.target.value); if (source) { setTitle(source.title); setScript(source.script); setRefs(source.references) } }}><option value="">Novo roteiro</option>{sources.map(s => <option key={s.id} value={String(s.id)}>{s.title}</option>)}</select></label>}<p className="text-sm text-[#8b949e]">Ao escolher um Reel histórico, você o associa explicitamente a esta empresa. Nenhum histórico será apagado.</p></>}
      <label className="block">Título<input required maxLength={300} className={field} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label className="block">Roteiro<textarea required rows={6} maxLength={20000} className={field} value={script} onChange={e => setScript(e.target.value)} /></label>
      <label className="block">Referência HTTPS (opcional)<input type="url" className={field} onChange={e => setRefs(old => [...old.filter(r => r.label !== 'Referência adicional'), ...(e.target.value ? [{ label: 'Referência adicional', reference: e.target.value }] : [])])} /></label>
      <div className="flex gap-2"><button className={button} disabled={busy}>Salvar roteiro</button><button type="button" className={button} onClick={() => setCreating(false)}>Cancelar</button></div>
    </form>}
    {!selected ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{rows.map(row => <button key={row.id} className={`${box} text-left min-h-28 hover:border-[#58a6ff]`} onClick={() => select(row.id)}><span className="block font-semibold">{row.title}</span><span className="block text-sm text-[#79c0ff]">{states[row.state] || row.state}</span><span className="block text-sm text-[#8b949e]">Roteiro v{row.script_revision} · {row.uploads.filter(u => u.status === 'complete').length} arquivos · {row.version_count ?? row.versions.length} prévias</span></button>)}{!loading && !rows.length && <p className={box}>Nenhuma gravação nesta empresa. Salve um roteiro para começar.</p>}</div> : recording && <>
      <button className={button} disabled={busy} onClick={() => select(null)}>← Todos os projetos</button>
      <section className={box}><div className="flex flex-wrap justify-between gap-2"><h3 className="text-lg font-semibold">{recording.title}</h3><span className="text-sm text-[#79c0ff]">{states[recording.state] || recording.state}</span></div><p className="text-sm text-[#8b949e]">Origem: {recording.origin_type} / {recording.origin_id} · lote {recording.batch}</p>
        {recording.scripts.map((s, index) => <details key={s.number} open={index === 0}><summary className="min-h-11 cursor-pointer py-2">Roteiro v{s.number}{index === 0 ? ' · atual' : ' · histórico preservado'}</summary><p className="whitespace-pre-wrap break-words">{s.text}</p><ul className="space-y-2 py-3">{s.references.map((ref, i) => <li key={i} className="break-all text-sm">{ref.reference.startsWith('https://') ? <a href={ref.reference} target="_blank" rel="noreferrer" className="text-[#79c0ff] underline">{ref.label}</a> : `${ref.label}: ${ref.reference}`}</li>)}</ul></details>)}
        <details><summary className="min-h-11 cursor-pointer py-2">Salvar nova versão do roteiro</summary><form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void run(async () => { accept(await api.post(`${root}/scripts`, { expected_revision: recording.revision, script: form.get('script'), references: recording.scripts[0].references })); setNotice('Nova versão salva. A aprovação anterior não autoriza esta versão.') }) }}><label>Roteiro<textarea name="script" required className={field} rows={6} defaultValue={recording.scripts[0].text} key={recording.script_revision} /></label><button className={button} disabled={busy}>Preservar como nova versão</button></form></details>
      </section>
      <section className={box}><h3 className="font-semibold">Brutos · vídeos, fotos e áudios</h3><p className="text-sm text-[#8b949e]">Arquivos ficam na pasta lógica desta gravação. Duplicatas são sinalizadas e preservadas. Enviar arquivos não inicia a edição.</p>
        {!recording.closed ? <><label className="block">Adicionar ou retomar arquivos<input type="file" multiple accept="video/mp4,video/quicktime,video/webm,image/jpeg,image/png,image/webp,audio/*" className={`${field} mt-2`} disabled={busy} onChange={e => { const files = Array.from(e.target.files || []); e.target.value = ''; if (files.length) void run(async () => { try { await uploadFiles(files) } finally { await reload() } }) }} /></label><p role="status" className="text-sm">{progress}</p></> : <button className={button} disabled={busy} onClick={() => void run(async () => { accept(await api.post(`${root}/reopen`, { expected_revision: recording.revision })); setExcludedSelection(recording.uploads.filter(upload => !lastAssets.some(asset => asset.id === upload.id)).map(upload => upload.id)); setChecks({}) })}>Adicionar mais brutos / nova edição</button>}
        <ol className="space-y-3">{recording.uploads.map((upload, i) => <li key={upload.id} className="rounded-lg border border-[#30363d] p-3"><div className="flex items-start gap-3">{upload.status === 'complete' && !recording.closed && <input type="checkbox" aria-label={`Incluir ${upload.name} na edição`} className="mt-3 h-5 w-5" checked={chosen.includes(upload.id)} onChange={e => setExcludedSelection(old => e.target.checked ? old.filter(id => id !== upload.id) : [...old, upload.id])} />}<div className="min-w-0 flex-1"><p className="break-words">{i + 1}. {upload.name}</p><p className="text-sm text-[#8b949e]">{upload.status === 'complete' ? 'Recebido' : upload.status === 'excluded' ? 'Envio incompleto excluído do lote; dados preservados' : `Recebendo: ${Math.round(upload.received / upload.declared_size * 100)}%`}{upload.duplicate_of ? ' · cópia idêntica preservada' : ''}</p>{upload.status === 'receiving' && <progress className="w-full" value={upload.received} max={upload.declared_size} aria-label={`Progresso ${upload.name}`} />}{upload.status === 'complete' && <a href={`${base}/api/recordings/${recording.id}/uploads/${upload.id}/file`} target="_blank" rel="noreferrer" className="inline-block min-h-11 py-2 text-sm text-[#79c0ff] underline">Conferir original</a>}</div></div>{!recording.closed && upload.status === 'complete' && upload.kind === 'video' && <fieldset disabled={busy || !chosen.includes(upload.id)} className="my-3 space-y-3"><legend className="text-sm">Trechos mantidos de {upload.name} · segundos no original</legend>{trimInput(upload.id).map((part, index) => <div key={index} className="grid items-end gap-3 sm:grid-cols-3"><label>Trecho {index + 1} · início<input type="number" min={0} step="any" className={field} value={part.start} onChange={e => setTrimInputs(old => ({ ...old, [upload.id]: trimInput(upload.id).map((item, n) => n === index ? { ...item, start: e.target.value } : item) }))} /></label><label>Fim (vazio só no último)<input type="number" min={0} step="any" className={field} value={part.end} onChange={e => setTrimInputs(old => ({ ...old, [upload.id]: trimInput(upload.id).map((item, n) => n === index ? { ...item, end: e.target.value } : item) }))} /></label><button className={button} disabled={trimInput(upload.id).length === 1} onClick={() => setTrimInputs(old => ({ ...old, [upload.id]: trimInput(upload.id).filter((_, n) => n !== index) }))}>Remover trecho {index + 1}</button></div>)}<button className={button} disabled={trimInput(upload.id).length >= 20} onClick={() => setTrimInputs(old => ({ ...old, [upload.id]: [...trimInput(upload.id), { start: trimInput(upload.id).at(-1)?.end || '0', end: '' }] }))}>Adicionar trecho mantido</button><p className="text-sm text-[#8b949e]">Os intervalos entre os trechos serão retirados. Mantenha ordem cronológica sem sobreposição. Até 20 trechos por vídeo.</p></fieldset>}{!recording.closed && <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || i === 0} aria-label={`Mover ${upload.name} para cima`} onClick={() => void run(() => move(i, -1))}>↑ Subir</button><button className={button} disabled={busy || i === recording.uploads.length - 1} aria-label={`Mover ${upload.name} para baixo`} onClick={() => void run(() => move(i, 1))}>↓ Descer</button>{upload.status === 'receiving' && <button className={button} disabled={busy} onClick={() => void run(async () => accept(await api.post(`${root}/uploads/${upload.id}/exclude`)))}>Excluir envio incompleto do lote</button>}</div>}</li>)}</ol>
        {!recording.closed && <><label className="block">Segundos por foto<input type="number" min={1} max={30} className={field} value={photoSeconds} onChange={e => setPhotoSeconds(Number(e.target.value))} /></label><p className="text-sm text-[#8b949e]">A primeira montagem une os itens selecionados na ordem acima, preserva áudio e enquadramento e usa tela preta para áudios avulsos. Ajuste início e fim de cada vídeo após conferir o original. O worker valida os limites pela duração real. Para retirar um erro interno, mantenha um trecho antes e outro depois. Legendas e efeitos avançados ainda exigem edição externa.</p><button className={`${button} w-full border-[#58a6ff]`} disabled={busy || invalidCuts || !chosen.length || recording.uploads.some(u => u.status === 'receiving')} onClick={() => void run(async () => { accept(await api.post(`${root}/close`, { expected_revision: recording.revision, upload_ids: chosen, photo_seconds: photoSeconds, edits: cuts })); setVersionId(''); setChecks({}) })}>Tudo enviado — começar edição</button></>}
        {!recording.closed && invalidCuts && <p role="alert" className="text-sm text-amber-300">Use intervalos em ordem, sem sobreposição; início a partir de zero, fim maior e vazio apenas no último trecho.</p>}
      </section>
      {!recording.closed && <VideoProjectEditor key={recording.id} assets={recording.uploads.filter(upload => upload.status === 'complete' && chosen.includes(upload.id))} script={recording.scripts[0].text} busy={busy || recording.uploads.some(upload => upload.status === 'receiving')} onProduce={(production, format) => void run(async () => { accept(await api.post(`${root}/produce`, { expected_revision: recording.revision, uploads_confirmed: true, upload_ids: chosen, production, format })); setVersionId(''); setChecks({}) })} />}
      {recording.versions.length > 0 && <section className={box}><h3 className="font-semibold">Prévia e feedback</h3><label className="block">Versão<select disabled={capturing || busy} className={field} value={version?.id || ''} onChange={e => { feedbackKey.current = null; setVersionId(e.target.value); setChecks({}); setRejectionReason(''); setFeedback(''); setAudio(null) }}>{recording.versions.map(v => <option key={v.id} value={v.id}>Prévia v{v.number} · roteiro v{v.script_revision} · {v.job.status}</option>)}</select></label>{version && <>
        {ready ? <video key={version.job.id} controls playsInline preload="metadata" src={`${base}/api/media/jobs/${version.job.id}/video`} className="mx-auto max-h-[65vh] w-full rounded-lg bg-black" /> : <p role="status">{version.job.last_error || (['failed', 'cancelled', 'retryable_failure'].includes(version.job.status) ? 'Montagem não concluída. Confira os brutos e abra uma nova edição.' : 'Lote fechado. A prévia aparecerá quando o worker concluir a montagem.')}</p>}
        {version.snapshot.production && <details><summary className="min-h-11 cursor-pointer py-2">Roteiro e entradas desta prévia</summary><p className="text-sm">{version.snapshot.production.entry_modes.join(' + ')}</p><p className="whitespace-pre-wrap break-words">{version.snapshot.production.script}</p></details>}
        <ul className="text-sm">{version.snapshot.assets.map(asset => <li key={asset.id}>{recording.uploads.find(upload => upload.id === asset.id)?.name || asset.id}: {asset.trim ? ranges(asset.trim).map(part => `${part.start_seconds}s → ${part.end_seconds ?? 'final'}`).join(' / ') : 'arquivo completo'}</li>)}</ul>
        {version.rejection && <p role="status" className="text-sm text-amber-300">Reprovada por {version.rejection.by}: {version.rejection.reason}. Reabra a edição e gere uma nova prévia; esta versão não pode ser aprovada.</p>}
        {!current && <p className="text-sm text-amber-300">Versão histórica preservada. A aprovação só pode ocorrer na versão atual com lote fechado.</p>}
        <p className="text-sm text-[#8b949e]">Feedback fica vinculado à prévia v{version.number}. Áudios são armazenados sem transcrição automática. O feedback não é aplicado automaticamente à montagem. Para ajustar trechos, reabra o lote, altere início/fim e gere uma nova prévia. Para ajustes avançados, envie uma exportação e selecione somente ela. Cada prévia exige nova conferência e aprovação.</p>
        <label className="block">Feedback em texto<textarea className={field} rows={3} value={feedback} onChange={e => { feedbackKey.current = null; setFeedback(e.target.value) }} /></label>
        <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={() => void run(capture)}>{capturing ? 'Parar gravação de áudio' : 'Gravar feedback em áudio'}</button><label className="block text-sm">Ou anexar áudio<input type="file" accept="audio/*" className="block max-w-full py-2" disabled={busy || capturing} onChange={e => { feedbackKey.current = null; setAudio(e.target.files?.[0] || null) }} /></label></div>{audio && <AudioPreview file={audio} />}
        <button className={button} disabled={busy || capturing || (!feedback.trim() && !audio)} onClick={() => void run(async () => { const data = new FormData(); feedbackKey.current ||= crypto.randomUUID(); data.set('client_key', feedbackKey.current); data.set('text', feedback); if (audio) data.set('audio', audio); await binary(`${root}/versions/${version.id}/feedback`, 'POST', data); feedbackKey.current = null; setFeedback(''); setAudio(null); await reload(); setNotice('Feedback salvo nesta versão.') })}>Salvar feedback na v{version.number}</button>
        <ul className="space-y-3">{recording.feedback.filter(f => f.version_id === version.id).map(f => <li key={f.id} className="border-t border-[#30363d] pt-3"><p className="text-xs text-[#8b949e]">{new Date(f.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap break-words">{f.text}</p>{f.audio_url && <audio controls preload="none" src={`${base}${f.audio_url}`} className="max-w-full" />}</li>)}</ul>
        {current && ready && !version.rejection && (!version.snapshot.production || version.creative_review?.eligible) && <div className="space-y-3 border-t border-[#30363d] pt-4"><h4 className="font-semibold">Conferência humana desta prévia</h4>{version.qa_valid ? <p className="text-sm text-green-300">Conferência registrada para o arquivo atual.</p> : <>{Object.entries(qaLabels).map(([key, label]) => <label key={key} className="flex min-h-11 items-center gap-3"><input type="checkbox" checked={Boolean(checks[key])} onChange={e => setChecks(old => ({ ...old, [key]: e.target.checked }))} className="h-5 w-5" />{label}</label>)}<button className={button} disabled={busy || !Object.keys(qaLabels).every(key => checks[key])} onClick={() => void run(async () => accept(await api.post(`${root}/versions/${version.id}/qa`, { render_sha256: version.job.render_sha256, checks })))}>Registrar conferência do arquivo</button></>}{version.qa_valid && <MediaReleasePanel key={version.job.id} job={version.job} onChange={() => void reload()} />}</div>}
        {current && ready && !version.rejection && <div className="space-y-3 border-t border-[#30363d] pt-4"><label className="block">Motivo da reprovação<textarea className={field} rows={2} maxLength={2000} value={rejectionReason} onChange={e => setRejectionReason(e.target.value)} /></label><button className={button} disabled={busy || !rejectionReason.trim()} onClick={() => void run(async () => { accept(await api.post(`${root}/versions/${version.id}/reject`, { expected_revision: recording.revision, render_sha256: version.job.render_sha256, reason: rejectionReason })); setChecks({}); setRejectionReason(''); setNotice('Reprovação registrada. Reabra a edição para gerar outra prévia.') })}>Reprovar esta prévia</button><p className="text-sm text-[#8b949e]">Revoga a conferência e a aprovação desta versão. Posts já enviados ao destino exigem revisão no destino.</p></div>}
        {current && ready && version.snapshot.production && <CreativeReviewPanel key={version.id} root={root} versionId={version.id} busy={busy} summary={version.creative_review} onSubmit={review => void run(async () => { accept(await api.post(`${root}/versions/${version.id}/creative-review`, { expected_revision: recording.revision, review })); setChecks({}); setNotice('Revisão registrada para esta versão; confira a elegibilidade antes da aprovação final.') })} />}
        {version.release && <ul className="text-sm">{Object.entries(version.release.progress.channels || {}).map(([key, target]) => <li key={key} className="break-words">{key}: {target.state}{target.error ? ` · ${target.error}` : ''}</li>)}</ul>}
      </>}</section>}
    </>}
  </div>
}
function AudioPreview({ file }: { file: File }) {
  const element = useRef<HTMLAudioElement | null>(null)
  useEffect(() => { const next = URL.createObjectURL(file); if (element.current) element.current.src = next; return () => URL.revokeObjectURL(next) }, [file])
  return <audio ref={element} controls className="max-w-full" />
}
