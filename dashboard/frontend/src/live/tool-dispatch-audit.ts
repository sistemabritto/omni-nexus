// Metadata-only trace. No parameters/results/errors are passed to persist().
export type ToolStage='received'|'dispatch'|'response'|'error'|'send_attempt'|'sent_to_sdk'|'send_error'|'cancelled'|'duplicate'|'instrumented'
type Call={tool_name:string;tool_call_id:string;parameters:Record<string,unknown>}
type Entry={name:string;signature:string;done:boolean;outcome:Promise<{result:string;is_error:boolean}|null>}
const names=new Set(['read_current_omni_session','search_omni_context','request_internal_task','read_internal_task_status','cancel_internal_task'])
export class AuditedToolDispatcher {
  private seen=new Map<string,Entry>();private closed=false;private auditWarned=false
  private persist:(id:string,name:string,stage:ToolStage,signal?:AbortSignal)=>Promise<void>
  private ready:()=>Promise<void>
  private execute:(call:Call)=>Promise<string>
  private send:(value:{type:'client_tool_result';tool_call_id:string;result:string;is_error:boolean})=>void
  private active:()=>boolean
  private unavailable:()=>void
  private auditTimeoutMs:number
  constructor(persist:(id:string,name:string,stage:ToolStage,signal?:AbortSignal)=>Promise<void>,
    ready:()=>Promise<void>,execute:(call:Call)=>Promise<string>,
    send:(value:{type:'client_tool_result';tool_call_id:string;result:string;is_error:boolean})=>void,
    active:()=>boolean,unavailable:()=>void,auditTimeoutMs=200){
    this.persist=persist;this.ready=ready;this.execute=execute
    this.send=send;this.active=active;this.unavailable=unavailable
    this.auditTimeoutMs=Math.max(1,Math.min(auditTimeoutMs,1000))
  }
  private async trace(id:string,name:string,stage:ToolStage){
    const controller=typeof AbortController==='undefined'?undefined:new AbortController()
    let timer:ReturnType<typeof setTimeout>|undefined
    try{
      await Promise.race([
        Promise.resolve().then(()=>this.persist(id,name,stage,controller?.signal)),
        new Promise<never>((_resolve,reject)=>{timer=setTimeout(()=>{controller?.abort();reject(Error('audit_timeout'))},this.auditTimeoutMs)}),
      ])
    }catch{
      if(!this.auditWarned){this.auditWarned=true;try{this.unavailable()}catch{}}
    }finally{if(timer!==undefined)clearTimeout(timer)}
  }
  instrument(){return this.closed?Promise.resolve():this.trace('__live_audit_session__','session','instrumented')}
  private alive(){return !this.closed&&this.active()}
  private async emit(id:string,name:string,outcome:{result:string;is_error:boolean}){
    if(!this.alive()){await this.trace(id,name,'cancelled');return}
    await this.trace(id,name,'send_attempt')
    if(!this.alive()){await this.trace(id,name,'cancelled');return}
    try{this.send({type:'client_tool_result',tool_call_id:id,...outcome})}
    catch{await this.trace(id,name,'send_error');return}
    await this.trace(id,name,'sent_to_sdk') // sendMessage returned; no provider ACK exists here.
  }
  handle(call:Call):Promise<void>{
    if(!call||typeof call.tool_call_id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(call.tool_call_id)){this.unavailable();return Promise.resolve()}
    const id=call.tool_call_id,existing=this.seen.get(id),name=names.has(call.tool_name)?call.tool_name:'unsupported',signature=JSON.stringify(call.parameters)??''
    if(existing&&(existing.name!==name||existing.signature!==signature)){return this.trace(id,existing.name,'duplicate').then(()=>this.emit(id,existing.name,{result:'Identificador de ferramenta reutilizado com outro pedido.',is_error:true})).catch(()=>this.unavailable())}
    if(existing){
      return existing.outcome.then(async outcome=>{await this.trace(id,existing.name,'duplicate');if(outcome)await this.emit(id,existing.name,outcome)}).catch(()=>this.unavailable())
    }
    if(this.closed)return Promise.resolve()
    if(this.seen.size>=256)return this.trace(id,name,'received').then(()=>this.trace(id,name,'error')).then(()=>this.emit(id,name,{result:'Limite de ferramentas desta conexão atingido. Reconecte para continuar.',is_error:true})).catch(()=>this.unavailable())
    const entry:Entry={name,signature,done:false,outcome:Promise.resolve(null)}
    this.seen.set(id,entry)
    entry.outcome=(async()=>{
      await this.trace(id,name,'received') // Bounded best effort before tool HTTP; telemetry never gates execution.
      let outcome:{result:string;is_error:boolean}
      try{
        await this.ready()
        if(!this.alive()){await this.trace(id,name,'cancelled');return null}
        if(name==='unsupported')throw Error('unsupported')
        await this.trace(id,name,'dispatch')
        if(!this.alive()){await this.trace(id,name,'cancelled');return null}
        const result=await this.execute(call)
        if(result.length>24000)throw Error('budget')
        await this.trace(id,name,'response')
        outcome={result,is_error:false}
      }catch{
        await this.trace(id,name,'error')
        outcome={result:'Contexto indisponível ou não autorizado.',is_error:true}
      }
      if(!this.alive()){await this.trace(id,name,'cancelled');return null}
      return outcome
    })().finally(()=>{entry.done=true})
    return entry.outcome.then(outcome=>outcome?this.emit(id,name,outcome):undefined).catch(()=>{this.unavailable();if(this.alive())try{this.send({type:'client_tool_result',tool_call_id:id,result:'Não foi possível confirmar o diagnóstico da ferramenta.',is_error:true})}catch{}})
  }
  close(){this.closed=true;for(const [id,entry] of this.seen)if(!entry.done)void this.trace(id,entry.name,'cancelled').catch(()=>this.unavailable());this.seen.clear()}
}
