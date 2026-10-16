// Sistema Britto squad entry points; stable agent URLs and permissions retained.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Lock } from 'lucide-react'
import { api } from '../lib/api'
import { AgentAvatar } from '../components/AgentAvatar'
import { agentChoice, matchesAgent, partitionSquad, squadEntrances, squadEntryLabel, type CatalogAgent } from '../live/live-agent-catalog'
import './SquadEntrances.css'

type Agent = CatalogAgent & {memory_count?:number}
export default function Agents(){
  const [agents,setAgents]=useState<Agent[]>([]),[loading,setLoading]=useState(true)
  const [error,setError]=useState(false),[query,setQuery]=useState(''),[retry,setRetry]=useState(0)
  useEffect(()=>{let alive=true
    api.get('/agents').then(data=>{if(alive){setAgents(Array.isArray(data)?data:[]);setError(false)}})
      .catch(()=>{if(alive)setError(true)}).finally(()=>{if(alive)setLoading(false)})
    return()=>{alive=false}
  },[retry])
  const choices=agents.map(agent=>({...agentChoice(agent.name,agents),agent}))
  const {principal,specialists}=partitionSquad(choices)
  const searching=!!query.trim(),found=choices.filter(choice=>matchesAgent(choice,query)||squadEntryLabel(choice.slug,choice.name).toLocaleLowerCase('pt-BR').includes(query.toLocaleLowerCase('pt-BR')))
  function card(choice:typeof choices[number]){
    const entry=squadEntrances[choice.slug]
    const body=<><AgentAvatar name={choice.slug} size={64}/><div><h2>{squadEntryLabel(choice.slug,choice.name)}</h2><p>{entry?.delivery||choice.role}</p>
      {entry&&<small>Apoio: {entry.assistant} · Revisão: {entry.reviewer}</small>}
      <span>{choice.agent.locked?<><Lock size={14}/> Sem acesso</>:'Abrir agente →'}</span></div></>
    return choice.agent.locked?<article key={choice.slug} className="squad-entry squad-entry-locked" aria-label={`${squadEntryLabel(choice.slug,choice.name)} · Sem acesso`}>{body}</article>:<Link key={choice.slug} className="squad-entry" to={`/agents/${choice.slug}`}>{body}</Link>
  }
  return <main className="squad-home">
    <header><p className="squad-eyebrow">SISTEMA BRITTO · OMNINEXUS</p><h1>Quem resolve o quê</h1><p>Comece pelo responsável da entrega. Apoios, revisores e especialistas continuam disponíveis quando precisar.</p></header>
    <label className="squad-search"><Search size={20}/><span className="sr-only">Buscar agente por nome ou função</span><input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Buscar por função ou nome"/></label>
    {loading?<p role="status">Carregando squad…</p>:error?<div role="alert"><p>Não foi possível carregar o squad.</p><button onClick={()=>{setLoading(true);setRetry(value=>value+1)}}>Tentar novamente</button></div>:searching?<section aria-label="Resultados da busca"><p role="status">{found.length} resultado(s)</p><div className="squad-grid">{found.map(card)}</div></section>:<>
      <section aria-label="Responsáveis principais"><h2 className="squad-section-title">Responsáveis principais</h2><div className="squad-grid">{principal.map(card)}</div>{!principal.length&&<p>Nenhum responsável principal disponível neste catálogo. Consulte os especialistas abaixo.</p>}</section>
      <details className="squad-specialists"><summary>Apoios, revisores e especialistas <span>{specialists.length}</span></summary><p>Escolha uma competência específica. O responsável da entrega continua com o acompanhamento; revisão exige independência de quem criou.</p><div className="squad-grid">{specialists.map(card)}</div></details>
    </>}
  </main>
}
