import { useEffect, useState, useSyncExternalStore } from 'react'
import { Send } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { loadManagedOptions } from './managed-context-client'
import { useCompanies } from '../context/CompanyContext'
import { Link } from 'react-router-dom'
import VoicePicker from './VoicePicker'
import { managedSession } from './managed-session'
import { safeWorkLink } from './continuity-session'
import VoiceFirstConversation from './VoiceFirstConversation'
import { voiceFirstBindings, copyConversationText } from './voice-first-bindings'
import './LiveConversation.css'
import './ManagedNexusLive.css'
type Options={companies:{id:number;name:string}[];agents:string[];consumptionApproved:boolean;presentationGroups?:Record<string,string[]>}
type Agent={name:string;description:string;locked?:boolean}
const display=(name:string)=>name.split('-').map(word=>word[0]?.toUpperCase()+word.slice(1)).join(' ')
function MessageComposer({disabled}:{disabled:boolean}){
  const [draft,setDraft]=useState('')
  function send(){if(!draft.trim())return;managedSession.send(draft);setDraft('')}
  return <form onSubmit={e=>{e.preventDefault();send()}}><label className="sr-only" htmlFor="live-message">Mensagem</label><textarea id="live-message" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Escreva para Nexus Live…" disabled={disabled} rows={2}/><button aria-label="Enviar mensagem" disabled={disabled||!draft.trim()}><Send size={18}/></button></form>
}
export default function ManagedNexusLive(){
  const {hasAgentAccess}=useAuth()
  const {activeCompanyId,activeCompany}=useCompanies()
  const state=useSyncExternalStore(managedSession.subscribe,managedSession.snapshot)
  const [options,setOptions]=useState<Options|null>(null),[agents,setAgents]=useState<Agent[]>([])
  const [agent,setAgent]=useState<string|null>(null),[access,setAccess]=useState('Verificando acesso pessoal…')
  const [checking,setChecking]=useState(false),[catalogLoading,setCatalogLoading]=useState(true)
  const [retry,setRetry]=useState(0)
  useEffect(()=>{
    let alive=true;const abort=new AbortController()
    void loadManagedOptions().then(data=>{if(alive){setOptions(data);setAccess(data.consumptionApproved?'Acesso disponível.':'O consumo da conversa ainda não foi liberado no servidor.')}}).catch(error=>{if(alive)setAccess(error.message)}).finally(()=>{if(alive)setChecking(false)})
    void fetch('/api/agents',{credentials:'include',signal:abort.signal}).then(async response=>{if(!response.ok)throw Error();const data=await response.json();if(alive){const list=Array.isArray(data)?data:Array.isArray(data.agents)?data.agents:[];setAgents(list.filter((item:Agent)=>item&&typeof item.name==='string'))}}).catch(()=>{}).finally(()=>{if(alive)setCatalogLoading(false)})
    return()=>{alive=false;abort.abort()}
  },[retry])
  const pendingWrite=state.continuity?.writeStatus==='saving'||state.continuity?.writeStatus==='error'
  const company=options?.companies.find(c=>c.id===activeCompanyId)
  const busy=state.phase!=='idle',selected=busy?state.agent:agent??(state.companyId===activeCompanyId?state.agent:'')
  const groups=options?.presentationGroups||{}
  const known=new Set(Object.values(groups).flat()),available=options?.agents||agents.filter(item=>!item.locked&&hasAgentAccess(item.name)).map(item=>item.name)
  const renderedGroups={...groups,'Não classificado':available.filter(name=>!known.has(name))}
  const description=agents.find(item=>item.name===selected)?.description?.split(/\n|Examples:/)[0]
  const canStart=!!(!pendingWrite&&activeCompany&&company&&available.includes(selected)&&options?.consumptionApproved)
  const bindings=voiceFirstBindings(managedSession,company?{companyId:company.id,company:company.name,agent:selected}:null,true)
  return <main className="live-immersive managed-live voice-first-page" data-voice-state={state.mic?'listening':'idle'}>
    <header className="live-heading"><div><span className="live-eyebrow">SISTEMA BRITTO</span><h1>OmniNexus Live</h1><p>Converse por voz. Encontre suas entregas aqui.</p></div><span className="live-prototype">{state.phase==='connected'?'Conectado':'Acesso pessoal'}</span></header>
    <section className="managed-context" aria-label="Contexto da conversa">
      <div className="managed-current-company"><span>Empresa do menu global</span><p>{activeCompany?.name||'Selecione uma empresa no menu global'}</p>{activeCompany&&options&&!company&&<small>Empresa selecionada indisponível para esta conversa.</small>}</div>
      <label>Squad · agente de contexto<select aria-label="Agente da conversa" disabled={busy||available.length===0} value={selected} onChange={e=>setAgent(e.target.value)}><option value="">{catalogLoading&&!available.length?'Carregando agentes…':available.length?'Selecione um agente':'Nenhum agente autorizado disponível'}</option>{Object.entries(renderedGroups).map(([group,names])=>{const list=names.filter(name=>available.includes(name));return list.length?<optgroup key={group} label={group}>{list.map(name=><option key={name} value={name}>{display(name)}</option>)}</optgroup>:null})}</select></label>
      <small>Agrupamento de apresentação configurado pelo administrador. <Link to="/inteligencia">Consultar agentes em Inteligência</Link>.</small>
      {selected&&<p className="managed-agent"><strong>{display(selected)}</strong><span>{description||'Função não disponível no catálogo atual.'}</span><small>Identidade: {selected} · Respostas: Nexus Live. O agente selecionado define o contexto. Pedidos internos dependem de autorização.</small></p>}
    </section>
    {!busy&&<section className="live-status" aria-label="Condições para iniciar"><p>{!options?access:!activeCompany?'Selecione uma empresa no menu global.':!company?'A empresa global não está disponível para esta conversa.':!available.includes(selected)?'Selecione um agente do squad.':!options.consumptionApproved?'O consumo da conversa ainda não foi liberado no servidor.':'Empresa e agente selecionados. A conexão será validada ao iniciar.'}</p>{(!options||!options.consumptionApproved)&&<button type="button" className="px-3 py-3 underline disabled:opacity-40" disabled={checking} onClick={()=>{setChecking(true);setOptions(null);setAccess('Verificando acesso pessoal…');setCatalogLoading(true);setRetry(value=>value+1)}}>{checking?'Verificando acesso…':'Verificar acesso novamente'}</button>}</section>}
    <VoiceFirstConversation key={`${activeCompanyId??'none'}:${selected}`}
      phase={state.phase} mic={state.mic} canStart={canStart}
      status={busy||state.company||state.contextChanged?state.status:access}
      contextLabel={`${busy?state.company:activeCompany?.name||'Escolha uma empresa'} · ${selected?display(selected):'Escolha um agente'}`}
      saveStatus={state.continuity?.writeStatus||'idle'} events={state.continuity?.events||[]} messages={state.messages}
      {...bindings} safeHref={safeWorkLink} copyText={text=>copyConversationText(text,navigator.clipboard)}
    ><MessageComposer key={activeCompanyId??'no-company'} disabled={state.phase!=='connected'}/></VoiceFirstConversation>
    <p className="live-privacy">Microfone somente ao ativar. Com continuidade habilitada, transcrições finais são salvas no OmniNexus. Tarefas internas dependem de autorização do servidor. Gravação do provedor e retenção seguem a configuração do agente ElevenLabs.</p>
    {company&&<VoicePicker key={company.id} companyId={company.id} busy={busy} connecting={state.phase==='connecting'} activeVoice={state.voiceName}/>}
    <nav className="managed-links" aria-label="Contexto operacional"><Link to="/cockpit">Sessões, jobs e memória</Link><Link to="/live/gemini">Protótipo Gemini</Link></nav>
  </main>
}
