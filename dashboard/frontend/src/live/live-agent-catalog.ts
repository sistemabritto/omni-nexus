export type CatalogAgent = {name:string;description?:string;locked?:boolean;catalog?:{display_name?:string;display_label?:string;function?:string;sector?:string;sector_id?:string;delivery_profile?:{purpose?:string;inputs?:string;deliverables?:string;acceptance?:string;methods?:string[]}}}
export type AgentChoice = {slug:string;name:string;role:string;sector:string;catalogued:boolean}
const text=(value:unknown,limit:number)=>typeof value==='string'?value.trim().slice(0,limit):''
export const displayAgentSlug=(name:string)=>name.split('-').map(word=>word[0]?.toUpperCase()+word.slice(1)).join(' ')
export function agentChoice(slug:string,agents:CatalogAgent[],legacy:Record<string,string[]>={}):AgentChoice {
  const item=agents.find(a=>a.name===slug),catalog=item?.catalog
  const alias=text(catalog?.display_name,120),name=text(catalog?.display_label,160)||alias,role=text(catalog?.delivery_profile?.purpose,300)||text(catalog?.function,300),sector=text(catalog?.sector,160)
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
  'clawdia-assistant':{function:'Operação',nickname:'Hera',delivery:'Organiza próximos passos, responsáveis e bloqueios.',assistant:'Atlas',reviewer:'Argos · pool independente'},
  'mako-marketing':{function:'Estratégia',nickname:'Orion',delivery:'Transforma fontes e hipóteses em um brief claro.',assistant:'Sage',reviewer:'Argos · pool independente'},
  'pixel-social-media':{function:'Conteúdo',nickname:'Dante',delivery:'Responde por roteiro e adaptação de conteúdo por canal.',assistant:'Orion',reviewer:'Argos · pool independente'},
  'canvas-designer':{function:'Direção visual',nickname:'Íris',delivery:'Define identidade, composição e direção de movimento.',assistant:'Vulcano',reviewer:'Argos · pool independente'},
  'bolt-executor':{function:'Engenharia',nickname:'Vulcano',delivery:'Implementa mudanças delimitadas e apresenta validação.',assistant:'Hawk',reviewer:'Argos · pool independente'},
  'oath-verifier':{function:'Qualidade',nickname:'Argos',delivery:'Coordena revisores independentes por domínio, capacidade e versão.',assistant:'Probe',reviewer:'Argos · pool independente'},
}
export const squadSupport:Record<string,{function:string;nickname:string}>={
  'atlas-project':{function:'Projetos',nickname:'Atlas'},
  'sage-strategy':{function:'Análise estratégica',nickname:'Sage'},
  'raven-critic':{function:'Crítica de planos',nickname:'Raven'},
  'hawk-debugger':{function:'Diagnóstico de bugs',nickname:'Hawk'},
  'lens-reviewer':{function:'Revisão de código',nickname:'Lens'},
  'probe-qa':{function:'Testes de uso',nickname:'Probe'},
}
export const squadEntryLabel=(slug:string,fallback:string)=>{
  const entry=squadEntrances[slug]||squadSupport[slug]
  return entry?`${entry.function} · ${entry.nickname}`:fallback
}
export function partitionSquad<T extends {slug:string}>(choices:T[]){
  const bySlug=new Map(choices.map(choice=>[choice.slug,choice]))
  return {principal:Object.keys(squadEntrances).flatMap(slug=>bySlug.has(slug)?[bySlug.get(slug)!]:[]),
    specialists:choices.filter(choice=>!squadEntrances[choice.slug])}
}
