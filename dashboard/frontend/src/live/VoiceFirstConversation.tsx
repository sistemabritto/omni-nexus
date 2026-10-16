import { useState, type ReactNode } from 'react'
import './VoiceFirstConversation.css'

type Entry={event_id:string;kind:string;text:string;source:string;revision:number;verified:boolean;retracted?:boolean;links?:{label:string;url:string}[]}
type Message={author:string;text:string}
export type VoiceFirstProps={
  phase:'idle'|'connecting'|'connected';mic:boolean;canStart:boolean;status:string;contextLabel:string
  saveStatus:'idle'|'saving'|'saved'|'error';events:readonly Entry[];messages:readonly Message[]
  onStart:()=>void;onToggleMic:()=>void;onEnd:()=>void;onRetrySave:()=>void;onNew?:()=>void
  safeHref:(url:string)=>string|null;copyText:(text:string)=>Promise<void>;children?:ReactNode
}

// Presentation only: no controller, network, storage, SDK or microphone API.
// Callbacks must remain the existing application's start/end/toggle/save actions.
export default function VoiceFirstConversation(props:VoiceFirstProps){
  const [copyStatus,setCopyStatus]=useState(''),[confirmNew,setConfirmNew]=useState(false)
  const useful=props.events.filter(event=>!event.retracted&&['progress','result'].includes(event.kind))
  const savedSpeech=props.events.filter(event=>!event.retracted&&event.kind==='transcript')
  const transcript=props.messages.length?props.messages:savedSpeech.map(event=>({author:event.source.startsWith('browser:user:')?'Você · salvo':'Assistente · salvo',text:event.text}))
  async function copy(text:string){try{await props.copyText(text);setCopyStatus('Texto copiado.')}catch{setCopyStatus('Não foi possível copiar. Selecione o texto para copiar manualmente.')}}
  return <section className="voice-first-review" aria-label="Conversa por voz">
    <header><h2>Nexus Live</h2><p>{props.contextLabel}</p></header>
    <div className="voice-first-controls" aria-label="Controles da conversa">
      {props.phase==='idle'?<button type="button" className="voice-first-primary" disabled={!props.canStart} onClick={props.onStart}>Retomar conversa</button>:<>
        <button type="button" className="voice-first-primary" disabled={props.phase!=='connected'} aria-pressed={props.mic} onClick={props.onToggleMic}>{props.phase==='connecting'?'Conectando…':props.mic?'Pausar microfone':'Falar'}</button>
        <button type="button" className="voice-first-end" onClick={props.onEnd}>{props.phase==='connecting'?'Cancelar conexão':'Encerrar áudio'}</button>
      </>}
    {props.onNew&&<div className="voice-first-options">
      <button type="button" disabled={!props.canStart||props.phase==='connecting'} aria-expanded={confirmNew} onClick={()=>setConfirmNew(true)}>Nova conversa</button>
      {confirmNew&&<div role="group" aria-label="Confirmar nova conversa"><p>{props.phase==='connected'?'O áudio atual será encerrado antes de começar outra conversa.':'Começar outra conversa nesta empresa?'}</p><button type="button" disabled={!props.canStart||props.phase==='connecting'} onClick={()=>{setConfirmNew(false);props.onNew?.()}}>{props.phase==='connected'?'Encerrar áudio e começar nova':'Começar nova conversa'}</button><button type="button" onClick={()=>setConfirmNew(false)}>Continuar na conversa atual</button></div>}
    </div>}
    </div>
    <p className="voice-first-hint">{props.phase==='idle'?'O microfone fica desligado até você tocar em Falar.':props.phase==='connecting'?'Preparando a conexão. Microfone desligado.':props.mic?'Microfone ligado.':'Microfone desligado.'}</p>
    <p role="status" aria-live="polite">{props.status}</p>
    {props.saveStatus==='saving'&&<small role="status">Salvando a conversa…</small>}
    {props.saveStatus==='saved'&&<small>Conversa salva.</small>}
    {props.saveStatus==='error'&&<div role="alert"><p>Há mensagens sem confirmação de gravação.</p><button type="button" onClick={props.onRetrySave}>Tentar salvar novamente</button></div>}
    {props.children&&<div className="voice-first-writing">{props.children}</div>}
    <section className="voice-first-materials" aria-label="Resultados e materiais">
      <h3>Resultados e materiais</h3>
      {useful.length?useful.map(event=><article key={event.event_id}>
        <strong>{event.kind==='result'?'Resultado':'Andamento'}</strong><p>{event.text}</p>
        {event.links?.map((link,index)=>{const href=props.safeHref(link.url);return href?<a key={index} href={href} target={href.startsWith('/api/live/file-results/')?'_blank':undefined} rel={href.startsWith('/api/live/file-results/')?'noopener noreferrer':undefined}>{link.label}</a>:null})}
        <button type="button" onClick={()=>void copy(event.text)}>Copiar texto</button>
        <details><summary>Fonte do registro</summary><small>{event.source} · revisão {event.revision} · {event.verified?'Registro verificado':'Declaração não verificada'}</small></details>
      </article>):<p>Seus links e resultados aparecerão aqui.</p>}
      <p role="status" aria-live="polite">{copyStatus}</p>
    </section>
    <details className="voice-first-transcript"><summary>Transcrição (opcional)</summary><p>{props.messages.length?'Falas desta conexão.':'Falas recuperadas do histórico salvo.'}</p>{transcript.length?transcript.map((message,index)=><article key={index}><strong>{message.author}</strong><p>{message.text}</p></article>):<p>Nenhuma fala disponível nesta visualização.</p>}</details>

  </section>
}
