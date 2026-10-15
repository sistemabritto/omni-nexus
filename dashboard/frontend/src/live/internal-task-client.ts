export type InternalTask={jobId:string;status:string;reference:string;text?:string;replayed?:boolean}
export type TaskAttempt={ticketId:string;operation:TaskOperation;originId:string;inFlight:boolean}
export type TaskOperation='summarize_ticket'|'draft_ticket'
const identifier=/^[A-Za-z0-9_-]{1,128}$/
const states=new Set(['pending','running','success','failed','cancel_requested','cancelled'])
const messages:Record<string,string>={live_tasks_disabled:'Tarefas internas desabilitadas nesta instalação.',continuity_disabled:'Continuidade desabilitada nesta instalação.',ticket_changed_or_gated:'O ticket mudou ou possui bloqueio/aprovação pendente. Nenhuma aprovação foi concedida.',scope_denied:'Tarefa indisponível ou não autorizada neste contexto.',idempotency_conflict:'O identificador deste pedido já foi usado com outro conteúdo.',invalid_internal_task:'Pedido de tarefa inválido.'}
export class InternalTaskError extends Error {retryable:boolean;constructor(message:string,retryable=false){super(message);this.retryable=retryable}}
function exact(value:Record<string,unknown>,keys:string[]){return value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===keys.sort().join(',')}
export function createInternalTaskClient(contextId:number,conversationId:string){
  if(!Number.isInteger(contextId)||contextId<=0||!identifier.test(conversationId))throw Error('Vínculo inválido.')
  async function post(action:string,extra:Record<string,unknown>={}){
    let response:Response
    try{response=await fetch(`/api/live/omni-context/${contextId}/${action}`,{method:'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversationId,...extra})})}catch{throw new InternalTaskError('Resposta não confirmada. Repetir este pedido usa o mesmo identificador, sem criar outra tentativa.',true)}
    const data=await response.json().catch(()=>null)
    if(!response.ok)throw new InternalTaskError(messages[data?.error]||'O servidor não confirmou esta operação. Verifique o status antes de outro pedido.',response.status>=500&&data?.error!=='live_tasks_disabled'&&data?.error!=='continuity_disabled')
    if(!data||typeof data.jobId!=='string'||!identifier.test(data.jobId)||!states.has(data.status)||data.reference!==`/api/live/tasks/${data.jobId}`)throw new InternalTaskError('Resposta incompatível. Repita o mesmo pedido para verificar a confirmação.',true)
    return {jobId:data.jobId,status:data.status,reference:data.reference,...(typeof data.text==='string'?{text:data.text.slice(0,12000)}:{}),...(typeof data.replayed==='boolean'?{replayed:data.replayed}:{})} as InternalTask
  }
  async function request(ticketId:string,operation:TaskOperation,originId:string){
    if(!identifier.test(ticketId)||!['summarize_ticket','draft_ticket'].includes(operation)||typeof originId!=='string'||!originId||originId.length>256)throw new InternalTaskError('Ticket, operação ou origem do pedido inválidos.')
    // Identity comes from the SDK call ID or a human action, never model parameters.
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(`${conversationId}\n${originId}`))
    const requestId='live_'+Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('')
    const payload={requestId,operation,ticketId};try{return await post('tasks',payload)}catch(error){if(error instanceof InternalTaskError&&error.retryable)return post('tasks',payload);throw error}
  }
  const status=(jobId:string,cancel=false)=>{if(!identifier.test(jobId))throw new InternalTaskError('Identificador da tarefa inválido.');return post(`tasks/${jobId}/${cancel?'cancel':'status'}`)}
  const result=async(jobId:string)=>{if(!identifier.test(jobId))throw new InternalTaskError('Identificador inválido.');const response=await fetch(`/api/live/tasks/${jobId}`,{credentials:'include',cache:'no-store'});const data=await response.json();if(!response.ok||data.jobId!==jobId||data.reference!==`/api/live/tasks/${jobId}`||!states.has(data.status))throw new InternalTaskError('Resultado indisponível ou não autorizado.');return {jobId,status:data.status,reference:data.reference,text:typeof data.output==='string'?data.output.slice(0,12000):typeof data.text==='string'?data.text.slice(0,12000):''} as InternalTask}
  return {request,status,result,async tool(name:string,parameters:Record<string,unknown>,sdkCallId:string){
    if(name==='request_internal_task'&&exact(parameters,['ticketId','operation'])&&typeof parameters.ticketId==='string'&&typeof parameters.operation==='string')return request(parameters.ticketId,parameters.operation as TaskOperation,sdkCallId)
    if(['read_internal_task_status','cancel_internal_task'].includes(name)&&exact(parameters,['jobId'])&&typeof parameters.jobId==='string')return status(parameters.jobId,name==='cancel_internal_task')
    throw new InternalTaskError('Ferramenta ou parâmetros não permitidos.')
  }}
}
