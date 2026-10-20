import { useEffect, useState, useSyncExternalStore } from 'react'
import { Users, Square } from 'lucide-react'
import { agentIdentity } from '../lib/agent-routes'
import { AgentAvatar } from '../components/AgentAvatar'
import LiveChat from './LiveChat'
import { PartySession, loadPartyOptions, type PartyOptions } from './party-session'

export default function PartyMode({companyId,agents,groups}:{companyId:number|null;agents:string[];groups:Record<string,string[]>}){
  const [session]=useState(()=>new PartySession())
  const state=useSyncExternalStore(session.subscribe,session.snapshot)
  const [options,setOptions]=useState<PartyOptions|null>(null),[error,setError]=useState(''),[selected,setSelected]=useState<string[]>([]),[retry,setRetry]=useState(0)
  useEffect(()=>{let alive=true;void loadPartyOptions().then(value=>{if(alive){setOptions(value);setError('')}}).catch(()=>{if(alive)setError('Não foi possível verificar o acesso ao Party Mode.')});return()=>{alive=false}},[retry])
  useEffect(()=>{if(companyId)void session.restore(companyId);return()=>session.detach()},[session,companyId])
  const participants=state.session?.agents||selected.filter(a=>agents.includes(a))
  const active=state.session?.rounds.find(r=>r.status==='pending'||r.status==='running')
  const limitReached=!!state.session&&state.session.rounds.length>=state.session.maxRounds
  const ready=!!(!limitReached&&companyId&&options?.enabled&&options.textExecutionEnabled&&options.consumptionApproved&&participants.length>=2&&participants.length<=3&&!state.busy&&!state.uncertain&&!active)
  const entries=Object.entries(groups).map(([label,names])=>[label,names.filter(n=>agents.includes(n))] as const).filter(([,names])=>names.length)
  const grouped=new Set(entries.flatMap(([,names])=>names)),ungrouped=agents.filter(a=>!grouped.has(a))
  if(ungrouped.length)entries.push(['Participantes autorizados',ungrouped])
  const problem=error||(!companyId?'Selecione uma empresa no menu.':options&&!options.enabled?'Party Mode está preparado, mas ainda desligado no servidor.':options&&!options.textExecutionEnabled?'A execução restrita de texto ainda não foi habilitada.':options&&!options.consumptionApproved?'O consumo de texto ainda não foi autorizado.':limitReached?'Esta conversa atingiu o limite de rodadas. Selecione Nova conversa para continuar.':'')
  function toggle(agent:string){setSelected(previous=>previous.includes(agent)?previous.filter(a=>a!==agent):previous.length<3?[...previous,agent]:previous)}
  return <div className="live-experience-layout live-party-layout">
    <section className="live-party-stage" aria-label="Participantes do Party Mode">
      <div className="live-party-intro"><Users size={28} aria-hidden="true"/><h1>Party Mode</h1><p>Reúna de dois a três agentes, inclusive de setores diferentes. Uma pergunta, contribuições em sequência.</p></div>
      <p className="live-party-limit">Prévia por texto · sem voz, ferramentas ou execução de tarefas. Cada participante vê somente o histórico desta conversa e sua própria identidade.</p>
      <div className="live-party-selection" aria-label="Seleção de participantes">
        {entries.map(([label,names])=><fieldset key={label} disabled={!!state.session||state.busy}><legend>{label}</legend>{names.map(agent=><label className="live-party-person" key={agent}><input type="checkbox" checked={participants.includes(agent)} disabled={!participants.includes(agent)&&participants.length>=3} onChange={()=>toggle(agent)}/><AgentAvatar name={agent} size={28}/><span>{agentIdentity(agent).name}</span>{participants.includes(agent)&&<small>{participants.indexOf(agent)+1}º a responder</small>}</label>)}</fieldset>)}
      </div>
      <p className="live-party-limit">{participants.length}/3 selecionados. A ordem de seleção define a rodada. Cada participante usa execução de texto, sujeita à política de consumo. Abrir esta tela não executa nada.</p>
      <div className="live-party-controls">{(active||state.busy)&&<button type="button" onClick={()=>void session.cancel()}><Square size={16}/>Cancelar rodada</button>}<button type="button" disabled={state.busy||!companyId} onClick={()=>{if(state.session)void session.refresh();else if(companyId)void session.restore(companyId)}}>Consultar estado</button>{state.session&&<button type="button" disabled={state.busy} onClick={()=>void session.reset()}>Nova conversa</button>}</div>
      {problem&&<div className="live-inline-notice" role="alert">{problem}<button type="button" onClick={()=>setRetry(n=>n+1)}>Verificar novamente</button></div>}
      <p className="live-inline-notice" role="status">{state.status.startsWith('Respondendo: ')?'Respondendo: '+agentIdentity(state.status.slice(13)).name:state.status}</p>
      {state.session&&<p className="live-party-limit">{state.session.rounds.length}/{state.session.maxRounds} rodadas. O histórico é salvo nesta empresa. Falha ou cancelamento não repete a rodada automaticamente.</p>}
    </section>
    <LiveChat agent={participants[0]||''} messages={(state.session?.messages||[]).map(m=>({author:m.agent?agentIdentity(m.agent).name:'Você',text:m.text,agent:m.agent||undefined}))} events={[]} disabled={!ready} sending={state.busy} onSend={text=>session.send(companyId!,participants,text)} heading="Conversa em grupo" subtitle="Texto · um agente por vez" emptyTitle="Reúna perspectivas diferentes." emptyDescription="Escolha os participantes e envie a primeira pergunta. O Live individual continua separado."/>
  </div>
}
