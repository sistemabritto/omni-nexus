import { useEffect, useReducer, useRef, useState } from 'react'
import { encodePCM, Playback } from './audio'
import { Mic, Square, AudioLines, ChevronDown, ShieldCheck } from 'lucide-react'
import './LiveConversation.css'
import { initialDiagnostics, modelDiagnostics, liveErrorMessage, reasonLabel } from './model-diagnostics'

export default function LiveConversation() {
  const [status, setStatus] = useState('Pronto para iniciar')
  const [active, setActive] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [diagnostics, diagnose] = useReducer(modelDiagnostics, initialDiagnostics)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/live/status', { credentials:'include', cache:'no-store', signal:controller.signal })
      .then(async response => { if (!response.ok) throw Error(); const value = await response.json(); if (!controller.signal.aborted) diagnose({type:'config',value}) })
      .catch(() => { if (!controller.signal.aborted) diagnose({type:'unavailable'}) })
    return () => controller.abort()
  }, [])
  const resources = useRef<{ socket?: WebSocket; stream?: MediaStream; context?: AudioContext; capture?: ScriptProcessorNode; playback?: Playback; timer?: ReturnType<typeof setTimeout> }>({})
  const generation = useRef(0)
  function stop() {
    generation.current++
    const r = resources.current; resources.current = {}
    clearTimeout(r.timer); r.capture?.disconnect(); r.playback?.stop(); r.stream?.getTracks().forEach(t => t.stop()); r.socket?.close(); void r.context?.close()
    setActive(false); diagnose({type:'stop'})
  }
  useEffect(() => () => { generation.current++; const r = resources.current; clearTimeout(r.timer); r.capture?.disconnect(); r.playback?.stop(); r.stream?.getTracks().forEach(t => t.stop()); r.socket?.close(); void r.context?.close() }, [])
  async function start() {
    stop(); diagnose({type:'reset'}); const id = generation.current
    setActive(true); setStatus('Verificando disponibilidade…'); setTranscript('')
    try {
      const response = await fetch('/api/live/status', { credentials: 'include', cache: 'no-store' })
      if (!response.ok) throw Error('Live indisponível. Verifique sua sessão e a liberação do backend.')
      const availability = await response.json()
      if (id !== generation.current) return
      diagnose({type:'config',value:availability})
      if (!availability.enabled || !availability.freeTierVerified) throw Error('Teste real bloqueado: plano gratuito ainda não verificado.')
      if (id !== generation.current) return
      // Both resources are requested in this click flow, never on mount/reconnect.
      const context = new AudioContext({ sampleRate: 16000 }); resources.current.context = context; await context.resume()
      if (id !== generation.current) return
      setStatus('Aguardando permissão do microfone…')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
      if (id !== generation.current) { stream.getTracks().forEach(t => t.stop()); return }
      resources.current.stream = stream
      if (context.sampleRate !== 16000) throw Error('Este navegador não disponibilizou captura em 16 kHz.')
      const playback = new Playback(context); resources.current.playback = playback
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/live/ws`)
      resources.current.socket = socket
      resources.current.timer = setTimeout(() => { if (id === generation.current) { stop(); setStatus('Tempo de conexão esgotado. Clique para tentar novamente.') } }, 15000)
      socket.onmessage = event => {
        if (id !== generation.current) return
        try {
          const message = JSON.parse(event.data)
          diagnose({type:'event',value:message})
          if (message.error) { stop(); setStatus(liveErrorMessage(message.error)); return }
          if (message.event === 'model_switch') setStatus('Trocando modelo antes de conectar…')
          if (message.status === 'ready' && !resources.current.capture) {
            clearTimeout(resources.current.timer)
            setStatus('Ouvindo — pode falar em português')
            const input = context.createMediaStreamSource(stream)
            // Minimal prototype. Replace with AudioWorklet before broad rollout.
            const capture = context.createScriptProcessor(2048, 1, 1); resources.current.capture = capture
            capture.onaudioprocess = event => {
              if (socket.readyState !== WebSocket.OPEN) return
              if (socket.bufferedAmount > 64000) { stop(); setStatus('Conexão lenta. Clique para reconectar.'); return }
              socket.send(JSON.stringify({ audio: encodePCM(event.inputBuffer.getChannelData(0)) }))
            }
            input.connect(capture); capture.connect(context.destination)
            resources.current.timer = setTimeout(() => { stop(); setStatus('Limite de teste de dois minutos atingido.') }, 120000)
          }
          if (message.status === 'reconnect_required') { stop(); setStatus(`Nova sessão necessária: ${reasonLabel(message.reason)}. Clique para iniciar; o contexto não será retomado.`); return }
          if (message.status === 'listening') setStatus('Ouvindo — pode falar em português')
          if (message.interrupted) { playback.stop(); setStatus('Ouvindo — resposta interrompida') }
          if (message.audio) { playback.play(message.audio); setStatus('Respondendo em português — você pode interromper falando') }
          if (message.transcript) setTranscript(previous => (previous + message.transcript).slice(-4000))
        } catch { stop(); setStatus('Falha na sessão. Clique para reconectar.') }
      }
      socket.onerror = () => { if (id === generation.current) { stop(); setStatus('Falha na conexão. Clique para reconectar.') } }
      socket.onclose = () => { if (id === generation.current) { stop(); setStatus('Sessão encerrada. Clique para reconectar.') } }
    } catch (error) {
      if (id === generation.current) { stop(); setStatus(error instanceof Error ? error.message : 'Não foi possível iniciar.') }
    }
  }
  const voiceState = active ? status.startsWith('Ouvindo') ? 'listening' : status.startsWith('Respondendo') ? 'speaking' : 'connecting' : 'off'
  const voiceLabel = voiceState === 'listening' ? 'Ouvindo você' : voiceState === 'speaking' ? 'Respondendo' : voiceState === 'connecting' ? 'Preparando conexão' : 'Microfone desligado'
  return <main className="live-immersive" data-voice-state={voiceState}>
    <header className="live-heading">
      <div><span className="live-eyebrow">OMNINEXUS LIVE</span><p>Conversa por voz · Português BR</p></div>
      <span className="live-prototype">Prévia</span>
    </header>
    <section className="live-stage" aria-labelledby="live-title">
      <div className="live-orbit" aria-hidden="true"><div className="live-orbit-ring" /><div className="live-core"><AudioLines size={52} strokeWidth={1.2} /></div></div>
      <div className="live-intro"><h1 id="live-title">Vamos conversar.</h1><p>Sua voz, no centro da conversa.</p></div>
      <div className="live-state"><span className="live-state-dot" aria-hidden="true" />{voiceLabel}</div>
      <p className="live-status" role="status" aria-live="polite" aria-atomic="true">{status}</p>
    </section>
    <div className="live-controls" role="group" aria-label="Controles da conversa">
      <button className="live-start" disabled={active} onClick={() => void start()}><Mic size={20} aria-hidden="true" />{active ? 'Conversa em andamento' : 'Iniciar conversa'}</button>
      <button className="live-stop" title="Encerrar e desligar microfone" aria-label="Encerrar e desligar microfone" disabled={!active} onClick={() => { stop(); setStatus('Microfone desligado. Clique para iniciar novamente.') }}><Square size={18} aria-hidden="true" /></button>
    </div>
    <p className="live-privacy"><ShieldCheck size={16} aria-hidden="true" /><span>Microfone só após seu clique. Até 2 minutos por sessão.<br />Reconexão manual · Sem ferramentas de produção.</span></p>
    <section className="live-models" aria-label="Modelo da conversa">
      <dl><div><dt>Configurado</dt><dd>{diagnostics.configuredModel || (diagnostics.unavailable ? 'Configuração indisponível' : diagnostics.loaded ? 'Não informado pelo servidor' : 'Consultando configuração…')}</dd></div><div><dt>Ativo nesta sessão</dt><dd>{diagnostics.activeModel || (diagnostics.attemptingModel ? `Conectando: ${diagnostics.attemptingModel}` : 'Nenhum modelo confirmado')}</dd></div></dl>
      <details><summary>Diagnóstico de conexão <ChevronDown size={14} aria-hidden="true" /></summary><div className="live-model-details">
        <p>Tentativa: {diagnostics.attempt ?? '—'} / {diagnostics.maxAttempts ?? 'não informado'}</p>
        <p>Fallbacks elegíveis: {diagnostics.fallbackModels.join(', ') || 'Nenhum informado'}</p>
        <p>Fallbacks bloqueados por falta de verificação de cota: {diagnostics.fallbackBlockedModels.join(', ') || 'Nenhum informado'}</p>
        {diagnostics.contextReset && <p>Nova sessão, sem retomada de contexto. Reconectar exige novo clique.</p>}
        <ol aria-label="Eventos desta sessão">{diagnostics.events.map((entry,index) => <li key={index}>{entry}</li>)}</ol>
        {!diagnostics.events.length && <p>Ainda não há eventos de conexão.</p>}
      </div></details>
    </section>
    <details className="live-transcript">
      <summary><span>Transcrição desta sessão</span><ChevronDown size={16} aria-hidden="true" /></summary>
      <div><p>{transcript || 'Ainda não há transcrição. O texto recebido durante a conversa aparecerá aqui.'}</p><small>Texto temporário desta página.</small></div>
    </details>
  </main>
}
