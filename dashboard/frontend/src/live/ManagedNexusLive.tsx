import LiveFileSources from './LiveFileSources'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { Send } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { loadManagedOptions } from './managed-context-client'
import { useCompanies } from '../context/CompanyContext'
import { Link } from 'react-router-dom'
import VoicePicker from './VoicePicker'
import LiveAgentSelector from './LiveAgentSelector'
import { agentChoice, type CatalogAgent } from './live-agent-catalog'
import { managedSession } from './managed-session'
import { safeWorkLink } from './continuity-session'
import VoiceFirstConversation from './VoiceFirstConversation'
import { voiceFirstBindings, copyConversationText } from './voice-first-bindings'
import './LiveConversation.css'
import './ManagedNexusLive.css'
type Options={companies:{id:number;name:string}[];agents:string[];consumptionApproved:boolean;presentationGroups?:Record<string,string[]>}
type Agent=CatalogAgent
function MessageComposer({disabled}:{disabled:boolean}){
  const [draft,setDraft]=useState('')
  function send(){if(!draft.trim())return;managedSession.send(draft);setDraft('')}
  return <form onSubmit={e=>{e.preventDefault();send()}}><label className="sr-only" htmlFor="live-message">Mensagem</label><textarea id="live-message" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Escreva para Nexus Live…" disabled={disabled} rows={2}/><button aria-label="Enviar mensagem" disabled={disabled||!draft.trim()}><Send size={18}/></button></form>
}
export default function ManagedNexusLive(){
  const {hasAgentAccess,user}=useAuth()
  const {activeCompanyId,activeCompany}=useCompanies()
  const state=useSyncExternalStore(managedSession.subscribe,managedSession.snapshot)
  const [options,setOptions]=useState<Options|null>(null),[agents,setAgents]=useState<Agent[]>([])
  const [agent,setAgent]=useState<string|null>(null),[access,setAccess]=useState('Verificando acesso pessoal…')
  const [checking,setChecking]=useState(false),[catalogLoading,setCatalogLoading]=useState(true)
  const [retry,setRetry]=useState(0),[catalogUnavailable,setCatalogUnavailable]=useState(false)
  useEffect(()=>{
    let alive=true;const abort=new AbortController()
    void loadManagedOptions().then(data=>{if(alive){setOptions(data);setAccess(data.consumptionApproved?'Acesso disponível.':'O consumo da conversa ainda não foi liberado no servidor.')}}).catch(error=>{if(alive)setAccess(error.message)}).finally(()=>{if(alive)setChecking(false)})
    void fetch('/api/agents',{credentials:'include',signal:abort.signal}).then(async response=>{if(!response.ok)throw Error();const data=await response.json();if(alive){const list=Array.isArray(data)?data:Array.isArray(data.agents)?data.agents:[];setAgents(list.filter((item:Agent)=>item&&typeof item.name==='string'));setCatalogUnavailable(!list.some((item:Agent)=>item&&typeof item.catalog?.display_name==='string'&&typeof item.catalog?.sector==='string'))}}).catch(()=>{if(alive){setAgents([]);setCatalogUnavailable(true)}}).finally(()=>{if(alive)setCatalogLoading(false)})
    return()=>{alive=false;abort.abort()}
  },[retry])
  const pendingWrite=state.continuity?.writeStatus==='saving'||state.continuity?.writeStatus==='error'
  const company=options?.companies.find(c=>c.id===activeCompanyId)
  const busy=state.phase!=='idle',selected=busy?state.agent:agent??(state.companyId===activeCompanyId?state.agent:'')
  const groups=options?.presentationGroups||{}
  const available=(options?.agents||agents.map(item=>item.name)).filter(name=>hasAgentAccess(name)&&!agents.find(item=>item.name===name)?.locked)
  const selectedChoice=agentChoice(selected,agents,groups)
  const canStart=!!(!pendingWrite&&activeCompany&&company&&available.includes(selected)&&options?.consumptionApproved)
  const bindings=voiceFirstBindings(managedSession,company?{companyId:company.id,company:company.name,agent:selected}:null,true)
  return <main className="live-immersive managed-live voice-first-page" data-voice-state={state.mic?'listening':'idle'}>
    <header className="live-heading"><div><span className="live-eyebrow">SISTEMA BRITTO</span><h1>OmniNexus Live</h1></div><span className="live-prototype">{state.phase==='connected'?'Conectado':state.phase==='connecting'?'Conectando…':'Desconectado'}</span></header>
    <details className="live-context-disclosure" open={!selected||undefined}><summary>{selected?`Contexto · ${selectedChoice.name}`:"Escolher agente"}</summary><section className="managed-context" aria-label="Contexto da conversa">
      <div className="managed-current-company"><span>Empresa do menu global</span><p>{activeCompany?.name||'Selecione uma empresa no menu global'}</p>{activeCompany&&options&&!company&&<small>Empresa selecionada indisponível para esta conversa.</small>}</div>
      <LiveAgentSelector allowed={available} agents={agents} legacyGroups={groups} selected={selected} disabled={busy} loading={catalogLoading} unavailable={catalogUnavailable} onSelect={setAgent} onRetry={()=>{setCatalogLoading(true);setRetry(value=>value+1)}}/>
      <small>Setores e funções são informações de apresentação; não habilitam ferramentas. <Link to="/inteligencia">Consultar agentes em Inteligência</Link>.</small>
      {selected&&<p className="managed-agent"><strong>{selectedChoice.name}</strong><span>{selectedChoice.role}</span><small>{selectedChoice.sector} · Identidade: {selected} · Respostas: Nexus Live. O agente selecionado define o contexto. Pedidos internos dependem de autorização.</small></p>}
    </section></details>
    {!busy&&(!options||!canStart)&&<section className="live-status" aria-label="Condições para iniciar"><p>{!options?access:!activeCompany?'Selecione uma empresa no menu global.':!company?'A empresa global não está disponível para esta conversa.':!available.includes(selected)?'Selecione um agente do squad.':!options.consumptionApproved?'O consumo da conversa ainda não foi liberado no servidor.':''}</p>{(!options||!options.consumptionApproved)&&<button type="button" className="px-3 py-3 underline disabled:opacity-40" disabled={checking} onClick={()=>{setChecking(true);setOptions(null);setAccess('Verificando acesso pessoal…');setCatalogLoading(true);setRetry(value=>value+1)}}>{checking?'Verificando acesso…':'Verificar acesso novamente'}</button>}</section>}
    <VoiceFirstConversation key={`${activeCompanyId??'none'}:${selected}`}
      phase={state.phase} mic={state.mic} canStart={canStart}
      status={busy||state.company||state.contextChanged?state.status:access}
      contextLabel={`${busy?state.company:activeCompany?.name||'Escolha uma empresa'} · Contexto: ${selected?selectedChoice.name:'Escolha um agente'}`}
      saveStatus={state.continuity?.writeStatus||'idle'} events={state.continuity?.events||[]} messages={state.messages}
      {...bindings} safeHref={safeWorkLink} copyText={text=>copyConversationText(text,navigator.clipboard)}
    ><MessageComposer key={activeCompanyId??'no-company'} disabled={state.phase!=='connected'}/></VoiceFirstConversation>
    <details className="live-preferences"><summary>Voz e configurações</summary>
      {company&&<VoicePicker key={company.id} companyId={company.id} busy={busy} connecting={state.phase==='connecting'} activeVoice={state.voiceName}/>}
      <p className="live-privacy">Microfone somente ao ativar. Com continuidade habilitada, transcrições finais são salvas no OmniNexus. Tarefas internas dependem de autorização do servidor. Gravação do provedor e retenção seguem a configuração do agente ElevenLabs.</p>
      <nav className="managed-links" aria-label="Contexto operacional"><Link to="/cockpit">Sessões, jobs e memória</Link><Link to="/live/gemini">Protótipo Gemini</Link></nav>
    </details>
    {user?.role==='admin'&&company&&<details className="live-admin-files"><summary>Arquivos · administração</summary><LiveFileSources key={`files:${company.id}`} companyId={company.id} company={company.name}/></details>}
  </main>
}
