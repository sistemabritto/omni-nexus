import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Check, Copy, Paperclip } from 'lucide-react'
import Markdown from '../components/Markdown'
import { AgentAvatar } from '../components/AgentAvatar'
import { agentIdentity } from '../lib/agent-routes'
import type { SavedEvent } from './continuity-session'
import { safeWorkLink } from './continuity-session'
type Message={author:string;text:string;kind?:string;agent?:string}
export default function LiveChat({messages,events,agent,disabled,sending,onSend,onAttach}:{messages:readonly Message[];events:readonly SavedEvent[];agent:string;disabled:boolean;sending:boolean;onSend:(text:string)=>Promise<boolean>;onAttach?:(file:File)=>Promise<string>}){
  const [draft,setDraft]=useState(''),[copied,setCopied]=useState(-1),[notice,setNotice]=useState(''),[attaching,setAttaching]=useState(false)
  const scroll=useRef<HTMLDivElement>(null),file=useRef<HTMLInputElement>(null)
  useEffect(()=>{scroll.current?.scrollTo({top:scroll.current.scrollHeight,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})},[messages.length,events.length])
  const useful=events.filter(e=>!e.retracted&&['result','progress'].includes(e.kind))
  const transcript:readonly Message[]=messages.length?messages:events.filter(e=>e.kind==='transcript'&&!e.retracted).map(e=>({author:e.source.startsWith('browser:user:')?'Você':agentIdentity(agent).name,text:e.text}))
  async function send(){if(!draft.trim()||disabled||sending)return;const value=draft;if(await onSend(value))setDraft(current=>current===value?'':current)}
  async function attach(value:File){if(!onAttach)return;setAttaching(true);try{setNotice(await onAttach(value))}catch{setNotice('Não foi possível anexar o arquivo. Tente novamente.')}finally{setAttaching(false);if(file.current)file.current.value=''}}
  return <section className="live-chat" aria-label="Chat da conversa">
    <header className="live-chat-heading"><span>Conversa</span><small>Voz e texto, no mesmo contexto</small></header>
    <div ref={scroll} className="live-chat-scroll" role="log" aria-label="Mensagens e materiais" aria-live="polite" aria-relevant="additions">
      {!transcript.length&&!useful.length&&<div className="live-chat-empty"><span>Uma conversa. Todo o seu squad.</span><p>Fale ou escreva. Links, arquivos e resultados ficam aqui.</p></div>}
      {transcript.map((message,index)=>message.kind==='handoff'?<p key={index} className="live-handoff-note"><span style={{background:agentIdentity(message.agent||agent).color}}/>{message.text}</p>:<article key={index} className={`live-chat-message ${message.author.startsWith('Você')?'from-user':'from-agent'}`}>
        {!message.author.startsWith('Você')&&<AgentAvatar name={message.agent||agent} size={28}/>}
        <div className="live-chat-message-body"><header>{message.author.replace(' · texto','').replace(' · voz','')}<button type="button" aria-label="Copiar mensagem" onClick={()=>void navigator.clipboard.writeText(message.text).then(()=>setCopied(index)).catch(()=>setNotice('Selecione o texto para copiar.'))}>{copied===index?<Check size={14}/>:<Copy size={14}/>}</button></header><Markdown>{message.text}</Markdown></div>
      </article>)}
      {useful.map(event=><article className="live-material" key={event.event_id}><small>{event.kind==='progress'?'Em andamento':'Material compartilhado'}</small><Markdown>{event.text}</Markdown>{event.links?.map((link,index)=>{const href=safeWorkLink(link.url);return href?<a key={index} href={href} target="_blank" rel="noopener noreferrer">{link.label} ↗</a>:null})}</article>)}
    </div>
    <form className="live-chat-composer" onSubmit={e=>{e.preventDefault();void send()}}>
      <label className="sr-only" htmlFor="live-message">Mensagem para o squad</label><textarea id="live-message" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Escreva, cole um prompt ou compartilhe um link…" disabled={disabled||sending} rows={2} maxLength={4000} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send()}}}/>
      <footer><div>{onAttach&&<><input ref={file} type="file" accept=".txt,.md,.csv,.json" hidden onChange={e=>{const f=e.target.files?.[0];if(f)void attach(f)}}/><button type="button" className="live-chat-attach" aria-label="Anexar arquivo de texto" disabled={disabled||attaching} onClick={()=>file.current?.click()}><Paperclip size={18}/><span>{attaching?'Anexando…':'Anexar'}</span></button></>}<span className="live-chat-key-hint">Shift + Enter para nova linha</span></div><button type="submit" className="live-chat-send" aria-label="Enviar mensagem" disabled={disabled||sending||!draft.trim()}><ArrowUp size={20}/></button></footer>
    </form>
    {notice&&<p className="live-inline-notice" role="status">{notice}</p>}
  </section>
}
