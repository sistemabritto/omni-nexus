import { useParams, Link } from 'react-router-dom'
import { useSyncExternalStore } from 'react'
import { ArrowLeft } from 'lucide-react'
import { useCompanies } from '../context/CompanyContext'
import { agentIdentity, agentSlug, agentHref } from '../lib/agent-routes'
import VoicePicker from '../live/VoicePicker'
import { managedSession } from '../live/managed-session'
import '../live/LiveExperience.css'
export default function AgentVoiceSettings(){
  const {name=''}=useParams(),slug=agentSlug(name),identity=agentIdentity(slug),{activeCompany}=useCompanies()
  const state=useSyncExternalStore(managedSession.subscribe,managedSession.snapshot)
  return <main className="live-experience"><header className="live-experience-header"><div><Link to={agentHref(slug)}><ArrowLeft size={16}/> {identity.name}</Link><h1>Voz de {identity.name}</h1><p>A preferência pertence a este agente na empresa selecionada.</p></div><Link to="/live">Voltar ao Live</Link></header>{activeCompany?<VoicePicker key={`${activeCompany.id}:${slug}`} companyId={activeCompany.id} agentName={slug} busy={state.phase!=='idle'} connecting={state.phase==='connecting'} activeVoice={state.agent===slug?state.voiceName:''}/>:<p>Selecione uma empresa para configurar a voz deste agente.</p>}</main>
}
