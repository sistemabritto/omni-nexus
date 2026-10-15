import { useEffect, useState, useSyncExternalStore } from 'react'
import { Radio, Mic, MicOff, Send, Square } from 'lucide-react'
import { useCompanies } from '../context/CompanyContext'
import { Link } from 'react-router-dom'
import VoicePicker from './VoicePicker'
import { managedSession } from './managed-session'
import './LiveConversation.css'
import './ManagedNexusLive.css'
type Options={companies:{id:number;name:string}[];agents:string[];consumptionApproved:boolean;presentationGroups?:Record<string,string[]>}
type Agent={name:string;description:string}
const display=(name:string)=>name.split('-').map(word=>word[0]?.toUpperCase()+word.slice(1)).join(' ')
export default function ManagedNexusLive(){
  const {activeCompanyId,activeCompany}=useCompanies()
  const state=useSyncExternalStore(managedSession.subscribe,managedSession.snapshot)
  const [options,setOptions]=useState<Options|null>(null),[agents,setAgents]=useState<Agent[]>([])
  const [agent,setAgent]=useState(''),[draft,setDraft]=useState(''),[access,setAccess]=useState('Verificando acesso pessoal…')
  useEffect(()=>{const abort=new AbortController();void fetch('/api/live/omni-context/options',{credentials:'include',cache:'no-store',signal:abort.signal}).then(async r=>{if(!r.ok)throw Error();const data=await r.json();if(!abort.signal.aborted){setOptions(data);setAccess(data.consumptionApproved?'Acesso disponível.':'Conversa real aguardando liberação de custo.')}}).catch(()=>{if(!abort.signal.aborted)setAccess('Acesso pessoal indisponível. O administrador precisa verificar o ID interno e as permissões.')});void fetch('/api/agents',{credentials:'include',signal:abort.signal}).then(r=>r.json()).then(data=>{if(!abort.signal.aborted)setAgents(Array.isArray(data)?data:data.agents||[])}).catch(()=>{});return()=>abort.abort()},[])
  useEffect(()=>{setDraft('')},[activeCompanyId])
  const company=options?.companies.find(c=>c.id===activeCompanyId)
  const busy=state.phase!=='idle',selected=busy?state.agent:agent
  const groups=options?.presentationGroups||{}
  const known=new Set(Object.values(groups).flat()),available=options?.agents||[]
  const renderedGroups={...groups,'Não classificado':available.filter(name=>!known.has(name))}
  const description=agents.find(item=>item.name===selected)?.description?.split(/\n|Examples:/)[0]
  function send(){if(!draft.trim())return;managedSession.send(draft);setDraft('')}
  return <main className="live-immersive managed-live" data-voice-state={state.mic?'listening':'idle'}>
    <header className="live-heading"><div><span className="live-eyebrow">SISTEMA BRITTO</span><p>Uma conversa · texto e voz · contexto explícito</p></div><span className="live-prototype">{state.phase==='connected'?'Conectado':'Acesso pessoal'}</span></header>
    <section className="managed-context" aria-label="Contexto da conversa">
      <div className="managed-current-company"><span>Empresa do menu global</span><p>{activeCompany?.name||'Selecione uma empresa no menu global'}</p>{activeCompany&&options&&!company&&<small>Empresa selecionada indisponível para esta conversa.</small>}</div>
      <label>Squad · agente de contexto<select aria-label="Agente da conversa" disabled={busy||!options} value={selected} onChange={e=>setAgent(e.target.value)}><option value="">Selecione um agente</option>{Object.entries(renderedGroups).map(([group,names])=>{const list=names.filter(name=>available.includes(name));return list.length?<optgroup key={group} label={group}>{list.map(name=><option key={name} value={name}>{display(name)}</option>)}</optgroup>:null})}</select></label>
      <small>Agrupamento de apresentação configurado pelo administrador. <Link to="/inteligencia">Consultar agentes em Inteligência</Link>.</small>
      {selected&&<p className="managed-agent"><strong>{display(selected)}</strong><span>{description||'Função não disponível no catálogo atual.'}</span><small>Identidade: {selected} · Respostas: Nexus Live. O agente selecionado fornece contexto; esta ferramenta não o executa.</small></p>}
    </section>
    <section className="live-stage"><div className="live-orbit" aria-hidden="true"><div className="live-orbit-ring"/><div className="live-core"><Radio size={42}/></div></div><div className="live-intro"><h1>OmniNexus Live</h1><p>Fale ou escreva. Continue na mesma conversa.</p></div><p className="live-status" role="status" aria-live="polite">{busy||state.company||state.contextChanged?state.status:access}</p>
      {state.runtimeSessionId&&<small className="managed-session-id">{state.company} · Sessão {state.runtimeSessionId}</small>}
    </section>
    <div className="live-controls">{!busy?<button disabled={!activeCompany||!company||!available.includes(agent)||!options?.consumptionApproved} onClick={()=>{if(company)void managedSession.start(company.id,company.name,agent)}}><Radio size={18}/>Iniciar conversa</button>:<><button disabled={state.phase!=='connected'} aria-pressed={state.mic} onClick={()=>void managedSession.toggleMic()}>{state.mic?<MicOff size={18}/>:<Mic size={18}/>} {state.mic?'Desligar microfone':'Ativar microfone'}</button><button onClick={()=>managedSession.end()}><Square size={16}/>Encerrar</button></>}</div>
    <p className="live-privacy">Microfone somente ao ativar. Sem ações de escrita. Gravação e retenção seguem a configuração do agente ElevenLabs.</p>
    <section className="managed-messages" aria-label="Conversa"><div role="log" aria-live="polite">{state.messages.length?state.messages.map((m,i)=><article key={i}><strong>{m.author}</strong><p>{m.text}</p></article>):<p>As mensagens aparecerão aqui. Nenhuma conversa demonstrativa.</p>}</div><form onSubmit={e=>{e.preventDefault();send()}}><label className="sr-only" htmlFor="live-message">Mensagem</label><textarea id="live-message" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Escreva para Nexus Live…" disabled={state.phase!=='connected'} rows={2}/><button aria-label="Enviar mensagem" disabled={state.phase!=='connected'||!draft.trim()}><Send size={18}/></button></form></section>
    {company&&selected&&<VoicePicker key={`${company.id}:${selected}`} companyId={company.id} agentName={selected} agentRole={description?.slice(0,240)||'Função não disponível no catálogo atual.'} busy={busy} connecting={state.phase==='connecting'} activeVoice={state.voiceName}/> }
    <nav className="managed-links" aria-label="Contexto operacional"><Link to="/cockpit">Sessões, jobs e memória</Link><Link to="/live/gemini">Protótipo Gemini</Link></nav>
  </main>
}
