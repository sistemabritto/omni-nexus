import { useEffect, useRef, useState } from 'react'
import { encodePCM, Playback } from './audio'

export default function LiveConversation() {
  const [status, setStatus] = useState('Pronto para iniciar')
  const [active, setActive] = useState(false)
  const [transcript, setTranscript] = useState('')
  const resources = useRef<{ socket?: WebSocket; stream?: MediaStream; context?: AudioContext; capture?: ScriptProcessorNode; playback?: Playback; timer?: ReturnType<typeof setTimeout> }>({})
  const generation = useRef(0)
  function stop() {
    generation.current++
    const r = resources.current; resources.current = {}
    clearTimeout(r.timer); r.capture?.disconnect(); r.playback?.stop(); r.stream?.getTracks().forEach(t => t.stop()); r.socket?.close(); void r.context?.close()
    setActive(false)
  }
  useEffect(() => () => { generation.current++; const r = resources.current; clearTimeout(r.timer); r.capture?.disconnect(); r.playback?.stop(); r.stream?.getTracks().forEach(t => t.stop()); r.socket?.close(); void r.context?.close() }, [])
  async function start() {
    stop(); const id = generation.current
    setActive(true); setStatus('Verificando disponibilidade…'); setTranscript('')
    try {
      const response = await fetch('/api/live/status', { credentials: 'include', cache: 'no-store' })
      if (!response.ok) throw Error('Live indisponível. Verifique sua sessão e a liberação do backend.')
      const availability = await response.json()
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
          if (message.error) throw Error('Sessão indisponível. Corrija a configuração no servidor e tente novamente.')
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
          if (message.status === 'reconnect_required') { stop(); setStatus('O servidor solicitou uma nova sessão. Clique para reconectar.'); return }
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
  return <main style={{ maxWidth: 720, margin: '40px auto', padding: 24, fontFamily: 'system-ui', lineHeight: 1.6 }}>
    <h1>OmniNexus Live</h1><p>Converse por voz em português brasileiro. Protótipo sem ferramentas de produção.</p>
    <p role="status" aria-live="polite">{status}</p>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <button style={{ minHeight: 44, padding: '8px 20px' }} disabled={active} onClick={() => void start()}>Iniciar conversa</button>
      <button style={{ minHeight: 44, padding: '8px 20px' }} disabled={!active} onClick={() => { stop(); setStatus('Microfone desligado. Clique para iniciar novamente.') }}>Encerrar e desligar microfone</button>
    </div>
    <p>O microfone só é solicitado após seu clique. Reconectar exige novo clique. Limite: dois minutos por sessão.</p>
    <h2>Transcrição temporária</h2><p>{transcript || 'A conversa aparecerá aqui.'}</p>
  </main>
}
