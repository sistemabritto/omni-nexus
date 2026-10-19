import { useCallback, useEffect, useState, useSyncExternalStore, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Mic, MicOff, Phone, PhoneOff, Settings2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useCompanies } from '../context/CompanyContext'
import { loadManagedOptions } from './managed-context-client'
import { managedSession } from './managed-session'
import { agentHref, agentIdentity } from '../lib/agent-routes'
import LiveAudioOrb from './LiveAudioOrb'
import LiveChat from './LiveChat'
import LiveApprovals from './LiveApprovals'
import './LiveExperience.css'
type Options={companies:{id:number;name:string}[];agents:string[];consumptionApproved:boolean}
export default function ManagedNexusLive(){
  const {hasAgentAccess}=useAuth(),{activeCompanyId,activeCompany}=useCompanies()
  const state=useSyncExternalStore(managedSession.subscribe,managedSession.snapshot)
  const [options,setOptions]=useState<Options|null>(null)
  const [chosen,setChosen]=useState('clawdia-assistant'),[error,setError]=useState(''),[retry,setRetry]=useState(0),[sending,setSending]=useState(false),[speaking,setSpeaking]=useState(false)
  useEffect(()=>{let alive=true;void loadManagedOptions().then(value=>{if(alive){setOptions(value);setError('')}}).catch(e=>{if(alive){setOptions(null);setError(e.message)}});return()=>{alive=false}},[retry])
  const available=(options?.agents||[]).filter(name=>hasAgentAccess(name))
  const connected=state.phase==='connected',busy=state.phase!=='idle'
  const selected=busy?state.agent:available.includes(chosen)?chosen:available[0]||''
  const identity=agentIdentity(selected),company=options?.companies.find(c=>c.id===activeCompanyId)
  const pending=state.continuity?.writeStatus==='saving'||state.continuity?.writeStatus==='error'
  const canStart=!!(company&&selected&&options?.consumptionApproved&&!pending)
  const onSpeaking=useCallback((value:boolean)=>setSpeaking(value),[])
  const status=state.phase==='connecting'?'Conectando':connected?speaking?`${identity.name} está falando`:state.mic?'Ouvindo você':'Microfone pausado':'Pronto para conversar'
  const problem=error||(!activeCompany?'Selecione uma empresa no menu.':options&&!company?'Empresa indisponível.':options&&!options.consumptionApproved?'As conversas ainda não foram liberadas no servidor.':'')
  async function send(text:string){
    setSending(true)
    try{if(!busy&&company&&canStart)await managedSession.start(company.id,company.name,selected);if(managedSession.snapshot().phase!=='connected')return false;return await managedSession.send(text)}finally{setSending(false)}
  }
  return <main className="live-experience" style={{'--agent-color':identity.color} as CSSProperties}>
    <header className="live-experience-header"><div><span className="live-experience-wordmark">OMNINEXUS <b>LIVE</b></span><small>{activeCompany?.name||'Sua empresa'}</small></div><span className={`live-connection-state ${connected?'is-connected':''}`}><i/>{connected?'Conectado':state.phase==='connecting'?'Conectando':'Disponível'}</span></header>
    <div className="live-experience-layout"><section className="live-stage" aria-label="Conversa por voz">
      <div className="live-agent-picker"><label htmlFor="live-agent">Conversar com</label><div><select id="live-agent" value={selected} disabled={!available.length||state.phase==='connecting'} onChange={e=>{const value=e.target.value;setChosen(value);if(connected)void managedSession.handoff(value,'Selecionado por você')}}>{available.map(slug=><option key={slug} value={slug}>{agentIdentity(slug).name}</option>)}</select>{selected&&<Link to={`${agentHref(selected)}/voice`} aria-label={`Configurar voz de ${identity.name}`}><Settings2 size={17}/></Link>}</div></div>
      <LiveAudioOrb frame={managedSession.audioFrame} phase={state.phase} color={identity.color} onSpeaking={onSpeaking}/>
      <div className="live-stage-caption"><h1>{identity.name||'Seu squad'}</h1><p role="status">{status}</p></div>
      <div className="live-stage-controls">{busy?<><button type="button" className="live-control-mic" disabled={!connected} aria-label={state.mic?'Pausar microfone':'Ativar microfone'} aria-pressed={state.mic} onClick={()=>void managedSession.toggleMic()}>{state.mic?<Mic size={21}/>:<MicOff size={21}/>}</button><button type="button" className="live-control-end" onClick={()=>managedSession.end()}><PhoneOff size={19}/><span>{connected?'Encerrar':'Cancelar'}</span></button></>:<><button type="button" className="live-control-start" disabled={!canStart} onClick={()=>{if(company)void managedSession.startVoice(company.id,company.name,selected)}}><Phone size={19}/><span>Conversar com {identity.name||'o squad'}</span></button><button type="button" className="live-text-start" disabled={!canStart} onClick={()=>{if(company)void managedSession.start(company.id,company.name,selected)}}>Só texto</button></>}</div>
      <p className="live-stage-hint">{busy?'Diga “quero falar com o Vulcano” para trocar de agente.':'Um clique para conectar e falar.'}</p>
      {problem&&<div className="live-inline-notice" role="alert">{problem}<button type="button" onClick={()=>{setOptions(null);setRetry(v=>v+1)}}>Verificar novamente</button></div>}
      {state.status&&!['Pode falar. Estou ouvindo.','Conversa conectada.','Conectando…'].includes(state.status)&&(busy||state.company)&&<p className="live-inline-notice" role="status">{state.status}</p>}
      {state.continuity?.writeStatus==='error'&&<div className="live-inline-notice" role="alert">Há mensagens aguardando gravação.<button type="button" onClick={()=>void managedSession.retryWrites()?.catch(()=>{})}>Tentar salvar</button></div>}
    </section><div className="live-conversation-column"><LiveApprovals connected={connected} companyId={activeCompanyId}/><LiveChat key={activeCompanyId??'none'} agent={selected} messages={state.messages} events={state.continuity?.events||[]} disabled={(!busy&&!canStart)||state.phase==='connecting'} sending={sending} onSend={send} onAttach={connected?file=>managedSession.attach(file):undefined}/></div></div>
  </main>
}
