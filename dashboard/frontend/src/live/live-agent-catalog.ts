export type CatalogAgent = {name:string;description?:string;locked?:boolean;catalog?:{display_name?:string;display_label?:string;function?:string;sector?:string;sector_id?:string}}
export type AgentChoice = {slug:string;name:string;role:string;sector:string;catalogued:boolean}
const text=(value:unknown,limit:number)=>typeof value==='string'?value.trim().slice(0,limit):''
export const displayAgentSlug=(name:string)=>name.split('-').map(word=>word[0]?.toUpperCase()+word.slice(1)).join(' ')
export function agentChoice(slug:string,agents:CatalogAgent[],legacy:Record<string,string[]>={}):AgentChoice {
  const item=agents.find(a=>a.name===slug),catalog=item?.catalog
  const alias=text(catalog?.display_name,120),name=text(catalog?.display_label,160)||alias,role=text(catalog?.function,300),sector=text(catalog?.sector,160)
  return {slug,name:squadEntryLabel(slug,name||displayAgentSlug(slug)),role:role||text(typeof item?.description==='string'?item.description.split(/\n|Examples:/)[0]:'',300)||'Função não disponível no catálogo atual.',
    sector:sector||Object.entries(legacy).find(([,names])=>Array.isArray(names)&&names.includes(slug))?.[0]||'Outros agentes autorizados',catalogued:!!(name&&role&&sector)}
}
const fold=(value:string)=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR')
export function agentChoices(allowed:string[],agents:CatalogAgent[],legacy:Record<string,string[]>={}) {
  // Metadata enriches only server-authorized slugs; it never adds an agent.
  return [...new Set(allowed)].filter(slug=>!agents.find(a=>a.name===slug)?.locked).map(slug=>agentChoice(slug,agents,legacy))
}
export function matchesAgent(choice:AgentChoice,query:string){return fold(`${choice.name} ${choice.role} ${choice.sector} ${choice.slug}`).includes(fold(query.trim()))}

// Shared entry points for Agents and Live. Presentation only, never ACL/dispatch.
export const squadEntrances:Record<string,{function:string;nickname:string;delivery:string;assistant:string;reviewer:string}>={
  'clawdia-assistant':{function:'Operação',nickname:'Clawdia',delivery:'Organiza próximos passos, responsáveis e bloqueios.',assistant:'Atlas',reviewer:'Oath'},
  'mako-marketing':{function:'Estratégia',nickname:'Mako',delivery:'Transforma fontes e hipóteses em um brief claro.',assistant:'Sage',reviewer:'Raven'},
  'pixel-social-media':{function:'Conteúdo',nickname:'Pixel',delivery:'Responde por roteiro e adaptação de conteúdo por canal.',assistant:'Mako',reviewer:'Oath'},
  'canvas-designer':{function:'Direção visual',nickname:'Canvas',delivery:'Define identidade, composição e direção de movimento.',assistant:'Bolt',reviewer:'Oath'},
  'bolt-executor':{function:'Engenharia',nickname:'Bolt',delivery:'Implementa mudanças delimitadas e apresenta validação.',assistant:'Hawk',reviewer:'Lens'},
  'oath-verifier':{function:'Qualidade',nickname:'Oath',delivery:'Revisa a entrega com critérios e evidências independentes.',assistant:'Probe',reviewer:'Raven'},
}
export const squadEntryLabel=(slug:string,fallback:string)=>{
  const entry=squadEntrances[slug]
  return entry?`${entry.function} · ${entry.nickname}`:fallback
}
export function partitionSquad<T extends {slug:string}>(choices:T[]){
  const bySlug=new Map(choices.map(choice=>[choice.slug,choice]))
  return {principal:Object.keys(squadEntrances).flatMap(slug=>bySlug.has(slug)?[bySlug.get(slug)!]:[]),
    specialists:choices.filter(choice=>!squadEntrances[choice.slug])}
}
