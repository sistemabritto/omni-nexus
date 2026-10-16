import { useId, useState } from 'react'
import { agentChoices, matchesAgent, type CatalogAgent } from './live-agent-catalog'
export default function LiveAgentSelector({allowed,agents,legacyGroups,selected,disabled,loading,unavailable,onSelect,onRetry}:{allowed:string[];agents:CatalogAgent[];legacyGroups:Record<string,string[]>;selected:string;disabled:boolean;loading:boolean;unavailable:boolean;onSelect:(slug:string)=>void;onRetry:()=>void}){
  const [query,setQuery]=useState(''),id=useId()
  const choices=agentChoices(allowed,agents,legacyGroups),matches=choices.filter(choice=>matchesAgent(choice,query))
  const selectedOutside=choices.find(choice=>choice.slug===selected&&!matches.some(match=>match.slug===selected))
  const groups=new Map<string,typeof choices>()
  for(const choice of matches)groups.set(choice.sector,[...(groups.get(choice.sector)||[]),choice])
  return <div className="live-agent-selector">
    <label htmlFor={`${id}-search`}>Buscar no squad<input id={`${id}-search`} type="search" value={query} disabled={disabled} onChange={e=>setQuery(e.target.value)} placeholder="Nome, função ou setor"/></label>
    <label htmlFor={`${id}-select`}>Squad · agente de contexto<select id={`${id}-select`} aria-label="Agente da conversa" aria-describedby={`${id}-help`} disabled={disabled||!choices.length} value={selected} onChange={e=>{if(e.target.value!==selected)onSelect(e.target.value)}}>
      <option value="">{loading&&!choices.length?'Carregando agentes…':choices.length?'Selecione um agente':'Nenhum agente autorizado disponível'}</option>
      {selectedOutside&&<optgroup label="Seleção atual"><option value={selectedOutside.slug}>{selectedOutside.name} — {selectedOutside.role}</option></optgroup>}
      {[...groups].sort(([a],[b])=>a.localeCompare(b,'pt-BR')).map(([sector,members])=><optgroup key={sector} label={sector}>{members.map(choice=><option key={choice.slug} value={choice.slug}>{choice.name} — {choice.role}</option>)}</optgroup>)}
    </select></label>
    <small id={`${id}-help`} role="status">{query?`${matches.length} agente(s) encontrado(s).${selectedOutside?' Seleção atual mantida fora da busca.':''}`:'Busque por quem faz o quê; os setores organizam a escolha.'}</small>
    {unavailable&&<><small role="status">Catálogo de setores indisponível. A lista autorizada continua disponível pelos identificadores.</small><button type="button" className="live-agent-retry" disabled={disabled||loading} onClick={onRetry}>{loading?'Carregando catálogo…':'Recarregar catálogo do squad'}</button></>}
  </div>
}
