import { useId, useState } from 'react'
import { agentChoices, matchesAgent, partitionSquad, squadEntryLabel, type CatalogAgent } from './live-agent-catalog'
export default function LiveAgentSelector({allowed,agents,legacyGroups,selected,disabled,loading,unavailable,onSelect,onRetry}:{allowed:string[];agents:CatalogAgent[];legacyGroups:Record<string,string[]>;selected:string;disabled:boolean;loading:boolean;unavailable:boolean;onSelect:(slug:string)=>void;onRetry:()=>void}){
  const [query,setQuery]=useState(''),[expanded,setExpanded]=useState(false),id=useId()
  const choices=agentChoices(allowed,agents,legacyGroups),matches=choices.filter(choice=>matchesAgent(choice,query))
  const selectedOutside=choices.find(choice=>choice.slug===selected&&!matches.some(match=>match.slug===selected))
  const {principal,specialists}=partitionSquad(matches)
  const visibleSpecialists=query.trim()||expanded?specialists:[]
  const selectedCollapsed=choices.find(choice=>choice.slug===selected&&!principal.some(match=>match.slug===selected)&&!visibleSpecialists.some(match=>match.slug===selected)&&!selectedOutside)
  return <div className="live-agent-selector">
    <label htmlFor={`${id}-search`}>Buscar no squad<input id={`${id}-search`} type="search" value={query} disabled={disabled} onChange={e=>setQuery(e.target.value)} placeholder="Nome, função ou setor"/></label>
    <label htmlFor={`${id}-select`}>Responsável ou especialista da conversa<select id={`${id}-select`} aria-label="Agente da conversa" aria-describedby={`${id}-help`} disabled={disabled||!choices.length} value={selected} onChange={e=>{if(e.target.value!==selected)onSelect(e.target.value)}}>
      <option value="">{loading&&!choices.length?'Carregando agentes…':choices.length?'Selecione um agente':'Nenhum agente autorizado disponível'}</option>
      {(selectedOutside||selectedCollapsed)&&<optgroup label="Seleção atual"><option value={(selectedOutside||selectedCollapsed)!.slug}>{squadEntryLabel((selectedOutside||selectedCollapsed)!.slug,(selectedOutside||selectedCollapsed)!.name)}</option></optgroup>}
      {principal.length>0&&<optgroup label="Responsáveis principais">{principal.map(choice=><option key={choice.slug} value={choice.slug}>{squadEntryLabel(choice.slug,choice.name)}</option>)}</optgroup>}
      {visibleSpecialists.length>0&&<optgroup label="Apoios, revisores e especialistas">{visibleSpecialists.map(choice=><option key={choice.slug} value={choice.slug}>{choice.name} — {choice.role}</option>)}</optgroup>}

    </select></label>
    <button type="button" className="live-agent-retry" disabled={disabled} aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?'Recolher apoios e especialistas':`Ver apoios e especialistas (${partitionSquad(choices).specialists.length})`}</button>
    <small id={`${id}-help`} role="status">{query?`${matches.length} agente(s) encontrado(s).${selectedOutside?' Seleção atual mantida fora da busca.':''}`:'Comece por um responsável. Busque qualquer agente autorizado ou abra os especialistas.'}</small>
    {unavailable&&<><small role="status">Catálogo de setores indisponível. A lista autorizada continua disponível pelos identificadores.</small><button type="button" className="live-agent-retry" disabled={disabled||loading} onClick={onRetry}>{loading?'Carregando catálogo…':'Recarregar catálogo do squad'}</button></>}
  </div>
}
