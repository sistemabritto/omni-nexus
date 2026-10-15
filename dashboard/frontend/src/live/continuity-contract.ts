// UI boundary for the opt-in authenticated backend. No provider, storage or identity inference.
export type ContinuityEntry={event_id:string;revision:number;kind:string;text:string;source:string;verified:boolean}
export type ContinuitySnapshot={status:'available';logicalConversationId:string;summaryRevision:number;kind:'untrusted_reference_data';current:ContinuityEntry[];truncated:boolean}
export type PreviousWork={reference:string;title:string;status:string;text:string;updatedAt:string;revision:string;comments:{reference:string;revision:string;authoredAt:string;text:string}[]}
export type WorkSearch={kind:'untrusted_reference_data';results:PreviousWork[];coverage:string;limit?:number}
export interface ContinuityGateway {resume():Promise<ContinuitySnapshot>;searchWork(query:string):Promise<WorkSearch>}
export class ContinuityUnavailable extends Error {}
export function createBoundContinuityGateway(contextId:number,providerConversationId:string):ContinuityGateway{
  if(!Number.isInteger(contextId)||contextId<=0||!/^[A-Za-z0-9_-]{1,128}$/.test(providerConversationId))throw new Error('Vínculo de conversa inválido.')
  async function post(action:string,extra:Record<string,unknown>={}){
    let response:Response
    try{response=await fetch(`/api/live/omni-context/${contextId}/${action}`,{method:'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversationId:providerConversationId,...extra})})}
    catch{throw new Error('Não foi possível consultar o contexto salvo. Tente novamente.')}
    const data=await response.json().catch(()=>null)
    if(response.status===404||data?.error==='continuity_disabled')throw new ContinuityUnavailable('Retomada ainda não habilitada nesta instalação.')
    if(!response.ok)throw new Error(response.status===403?'Acesso ao contexto ou aos trabalhos não autorizado.':'Não foi possível recuperar os registros. O contexto atual foi preservado.')
    return data
  }
  return {
    async resume(){const data=await post('continuity');if(data?.status!=='available'||data.kind!=='untrusted_reference_data'||!Array.isArray(data.current)||typeof data.logicalConversationId!=='string')throw new ContinuityUnavailable('Resposta de continuidade ainda não compatível com a interface.');return data as ContinuitySnapshot},
    async searchWork(query){const value=query.trim();if(!value||value.length>200)throw new Error('Use uma busca de 1 a 200 caracteres.');const data=await post('work-search',{query:value});if(data?.kind!=='untrusted_reference_data'||!Array.isArray(data.results))throw new Error('Resposta de trabalhos indisponível nesta versão.');return data as WorkSearch},
  }
}
export function ticketLink(reference:string):string|null {const match=/^\/api\/tickets\/([A-Za-z0-9_-]+)(?:\/comments#[A-Za-z0-9_-]+)?$/.exec(reference);return match?`/tickets/${encodeURIComponent(match[1])}`:null}
