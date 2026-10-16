export type CatalogAgent = {name:string;description?:string;locked?:boolean;catalog?:{display_name?:string;display_label?:string;function?:string;sector?:string;sector_id?:string}}
export type AgentChoice = {slug:string;name:string;role:string;sector:string;catalogued:boolean}
const text=(value:unknown,limit:number)=>typeof value==='string'?value.trim().slice(0,limit):''
export const displayAgentSlug=(name:string)=>name.split('-').map(word=>word[0]?.toUpperCase()+word.slice(1)).join(' ')
export function agentChoice(slug:string,agents:CatalogAgent[],legacy:Record<string,string[]>={}):AgentChoice {
  const item=agents.find(a=>a.name===slug),catalog=item?.catalog
  const alias=text(catalog?.display_name,120),name=text(catalog?.display_label,160)||alias,role=text(catalog?.function,300),sector=text(catalog?.sector,160)
  return {slug,name:name||displayAgentSlug(slug),role:role||text(typeof item?.description==='string'?item.description.split(/\n|Examples:/)[0]:'',300)||'Função não disponível no catálogo atual.',
    sector:sector||Object.entries(legacy).find(([,names])=>Array.isArray(names)&&names.includes(slug))?.[0]||'Outros agentes autorizados',catalogued:!!(name&&role&&sector)}
}
const fold=(value:string)=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR')
export function agentChoices(allowed:string[],agents:CatalogAgent[],legacy:Record<string,string[]>={}) {
  // Metadata enriches only server-authorized slugs; it never adds an agent.
  return [...new Set(allowed)].filter(slug=>!agents.find(a=>a.name===slug)?.locked).map(slug=>agentChoice(slug,agents,legacy))
}
export function matchesAgent(choice:AgentChoice,query:string){return fold(`${choice.name} ${choice.role} ${choice.sector} ${choice.slug}`).includes(fold(query.trim()))}
