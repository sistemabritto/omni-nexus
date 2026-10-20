// Party Mode is text-only. No voice SDK, microphone, tools, or provider on import.
export type PartyRound = {id:string;status:'pending'|'running'|'completed'|'failed'|'cancelled';next_index:number;error:string|null}
export type PartySnapshot = {id:string;companyId:number;agents:string[];mode:'text_no_tools';maxRounds:number;rounds:PartyRound[];messages:{id:number;round_id:string;agent:string|null;text:string}[]}
export type PartyOptions = {enabled:boolean;textExecutionEnabled:boolean;consumptionApproved:boolean;minParticipants:number;maxParticipants:number;maxRounds:number;mode:'text_no_tools'}
type State = {session:PartySnapshot|null;busy:boolean;status:string;uncertain:boolean}
type Api = (path:string,body?:unknown)=>Promise<unknown>
const errors:Record<string,string>={
  party_mode_disabled:'Party Mode ainda não foi liberado no servidor.',
  party_text_execution_disabled:'A execução de texto precisa ser habilitada pelo operador.',
  consumption_not_approved:'O consumo de texto ainda não foi autorizado no servidor.',
  party_scope_denied:'Uma empresa ou participante não está mais autorizado. Verifique a seleção.',
  operational_squad_unavailable:'O catálogo operacional está indisponível.',
  party_identity_unavailable:'A identidade de um participante ainda não está pronta.',
  party_round_busy:'Há uma rodada pendente. Consulte o estado antes de continuar.',
  party_round_limit:'Limite de rodadas atingido. Inicie uma nova conversa.',
  party_idempotency_conflict:'O identificador desta mensagem já foi usado com outro conteúdo.',
}
export const partyApi:Api = async(path,body)=>{
  const response=await fetch('/api/live/party'+path,{method:body===undefined?'GET':'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})
  const data=await response.json()
  if(!response.ok)throw Error(errors[data?.error]||(response.status===401?'Entre novamente para usar o Party Mode.':'A operação não foi confirmada. Consulte o estado antes de tentar de novo.'))
  return data
}
export async function loadPartyOptions():Promise<PartyOptions>{
  const data=await partyApi('/options') as PartyOptions
  if(!data||data.mode!=='text_no_tools'||typeof data.enabled!=='boolean'||typeof data.textExecutionEnabled!=='boolean'||typeof data.consumptionApproved!=='boolean'||data.minParticipants!==2||data.maxParticipants!==3)throw Error('Opções incompatíveis do Party Mode.')
  return data
}
export class PartySession {
  private state:State={session:null,busy:false,status:'Escolha de dois a três participantes.',uncertain:false}
  private generation=0
  private listeners=new Set<()=>void>()
  private api:Api
  constructor(api:Api=partyApi){this.api=api}
  snapshot=()=>this.state
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener)}}
  private patch(value:Partial<State>){this.state={...this.state,...value};this.listeners.forEach(listener=>listener())}
  private base(){return '/sessions/'+this.state.session!.id}
  private accept(value:unknown):PartySnapshot{
    const s=value as PartySnapshot
    if(!s||s.mode!=='text_no_tools'||!Array.isArray(s.agents)||!Array.isArray(s.rounds)||!Array.isArray(s.messages))throw Error('Estado incompatível do Party Mode.')
    return s
  }
  async restore(companyId:number){
    const generation=++this.generation
    this.patch({session:null,busy:true,uncertain:false,status:'Buscando a conversa desta empresa…'})
    try{const data=await this.api('/sessions?companyId='+companyId) as {session:PartySnapshot|null};if(generation!==this.generation)return
      const session=data.session?this.accept(data.session):null
      this.patch({session,busy:false,status:session?'Histórico recuperado. Nenhuma rodada foi retomada automaticamente.':'Escolha de dois a três participantes.',uncertain:!!session?.rounds.some(r=>r.status==='running')})
    }catch(error){if(generation===this.generation)this.patch({busy:false,status:error instanceof Error?error.message:'Histórico indisponível.',uncertain:true})}
  }
  async send(companyId:number,agents:string[],text:string){
    if(this.state.busy||this.state.uncertain||!text.trim())return false
    const generation=++this.generation
    this.patch({busy:true,status:'Preparando rodada por texto…'})
    let accepted=false
    try{
      let session=this.state.session
      if(!session){session=this.accept(await this.api('/sessions',{companyId,agents}));if(generation!==this.generation)return false;this.patch({session})}
      if(session.companyId!==companyId)throw Error('A empresa da conversa mudou.')
      const base='/sessions/'+session.id
      const started=await this.api(base+'/rounds',{requestId:crypto.randomUUID(),text}) as {roundId:string;session:PartySnapshot}
      accepted=true
      if(generation!==this.generation){
        const stoppedGeneration=this.generation
        const stopped=this.accept(await this.api(base+'/rounds/'+started.roundId+'/cancel',{}))
        if(stoppedGeneration===this.generation&&this.state.session?.id===session.id)this.patch({session:stopped,busy:false,uncertain:false,status:'Rodada cancelada antes de iniciar as respostas.'})
        return true
      }
      session=this.accept(started.session);this.patch({session})
      while(generation===this.generation){
        const round=session.rounds.find(r=>r.id===started.roundId)
        if(!round||round.status!=='pending')break
        this.patch({status:'Respondendo: '+session.agents[round.next_index]})
        session=this.accept(await this.api(base+'/rounds/'+round.id+'/next',{expectedIndex:round.next_index}))
        if(generation!==this.generation)return true
        this.patch({session})
      }
      if(generation===this.generation){
        const round=session.rounds.find(r=>r.id===started.roundId)
        this.patch({busy:false,uncertain:round?.status==='running',status:round?.status==='completed'?'Rodada concluída. Cada resposta tem seu próprio participante.':round?.status==='failed'?'A rodada foi interrompida. Respostas confirmadas foram preservadas; a rodada não será repetida automaticamente.':round?.status==='running'?'Uma resposta está em andamento ou não foi confirmada. Consulte o estado.':'Rodada encerrada.'})
      }
      return accepted
    }catch(error){if(generation===this.generation)this.patch({busy:false,uncertain:true,status:error instanceof Error?error.message:'A rodada não foi confirmada. Consulte o estado.'});return accepted}
  }
  async refresh(){
    if(!this.state.session||this.state.busy)return
    const generation=this.generation
    try{const session=this.accept(await this.api(this.base()));if(generation!==this.generation)return
      this.patch({session,uncertain:session.rounds.some(r=>r.status==='running'),status:session.rounds.some(r=>r.status==='pending')?'Rodada pausada. Cancele-a antes de enviar outra mensagem.':session.rounds.some(r=>r.status==='running')?'A resposta continua em andamento ou não foi confirmada. Você pode cancelar sem repetir a execução.':'Estado atualizado.'})
    }catch(error){if(generation===this.generation)this.patch({status:error instanceof Error?error.message:'Estado indisponível.'})}
  }
  async cancel(){
    ++this.generation
    const wasBusy=this.state.busy,session=this.state.session,round=session?.rounds.find(r=>r.status==='running'||r.status==='pending')
    this.patch({busy:false,status:'Interrompendo a rodada…'})
    if(!session||!round){this.patch({status:session&&wasBusy?'Interrupção solicitada. Aguardando confirmação do estado da rodada.':'Rodada interrompida.',uncertain:!!session&&wasBusy});return}
    const generation=this.generation
    try{const result=this.accept(await this.api('/sessions/'+session.id+'/rounds/'+round.id+'/cancel',{}));if(generation===this.generation)this.patch({session:result,uncertain:false,status:'Rodada cancelada. Uma chamada já iniciada pode terminar, mas sua resposta será descartada.'})}
    catch{if(generation===this.generation)this.patch({uncertain:true,status:'Cancelamento não confirmado. Consulte o estado; nenhuma nova chamada será iniciada.'})}
  }
  async reset(){await this.cancel();if(this.state.uncertain)return;this.patch({session:null,status:'Escolha os participantes da nova conversa.'})}
  detach(){void this.cancel();++this.generation;this.patch({session:null,busy:false,uncertain:false})}
}
