// Client-tool glue only: no SDK import, token request, microphone or provider activation.
type Context = { contextId:number; runtimeSessionId:string; company:{id:number;name:string}; agentName:string }
export class LiveRequestError extends Error {
  constructor(message:string){super(message);this.name='LiveRequestError'}
}
const messages:Record<string,string>={
  operational_squad_unavailable:'O squad operacional não está disponível. Tente novamente; o catálogo geral não substitui esta seleção.',
  personal_access_not_configured:'O acesso Live ainda não foi configurado no servidor para seu usuário autenticado.',
  personal_access_denied:'Sua conta autenticada ainda não está autorizada para o Live.',
  permission_denied:'Sua conta não tem as permissões necessárias para iniciar o Live.',
  cookie_session_required:'Entre novamente no aplicativo para usar o Live com sua sessão autenticada.',
  unauthorized:'Sua sessão expirou. Entre novamente no aplicativo.',
  consumption_not_approved:'O consumo da conversa ainda não foi liberado no servidor.',
  provider_agent_not_configured:'O agente de voz ainda não foi configurado no servidor. A escolha do squad não substitui essa configuração.',
  provider_not_configured:'A integração de voz ainda não está configurada no servidor.',
  scope_denied:'A empresa ou o agente selecionado não está autorizado para esta conversa.',
  runtime_context_unavailable:'Não foi possível preparar a sessão do agente. Tente novamente.',
  provider_unavailable:'O provedor de voz não está disponível. Nenhuma conversa foi iniciada.',
  provider_or_saved_voice_unavailable:'O provedor ou a preferência de voz não está disponível. Verifique a configuração antes de iniciar.',
  voice_metadata_unavailable:'Não foi possível consultar a configuração da voz do destino. Tente novamente.',
  voice_not_in_account:'A voz do destino não está disponível na conta de voz configurada.',
  voice_not_compatible:'A voz do destino não está liberada ou compatível com o modelo de áudio configurado.',
  voice_override_disabled:'O agente de voz não permite selecionar a voz do destino.',
  voice_live_moderation_unsupported:'A voz do destino tem moderação ao vivo e não pode ser usada em Agents. Selecione outra voz compatível.',
  origin_forbidden:'A origem desta solicitação não foi aceita pelo servidor.',
  github_credential_not_configured:'GitHub sem credencial configurada. Configure o token no painel de Integrações; não envie pelo chat.',
  github_authentication_failed:'O GitHub recusou a autenticação. Confira a credencial no painel de Integrações.',
  github_permission_or_rate_limit:'O GitHub recusou a operação por permissão ou limite de requisições. Confira os escopos e o estado da integração.',
  github_resource_not_found:'O GitHub não encontrou esse recurso com a credencial atual. Confira proprietário, repositório, número e acesso a repositórios privados.',
  github_network_unavailable:'Não foi possível alcançar o GitHub. A leitura não foi concluída.',
  github_upstream_unavailable:'O GitHub não concluiu a operação. Consulte o estado antes de repetir uma alteração.',
  github_diff_changed:'O SHA da branch ou do PR mudou. Leia a versão atual antes de preparar outra solicitação.',
  approval_target_changed:'O alvo mudou depois da proposta. A alteração não foi aplicada; leia o estado atual e prepare uma nova proposta.',
  approval_expired:'A aprovação expirou. Confira o estado atual antes de preparar uma nova proposta.',
  web_search_not_configured:'A pesquisa externa está sem credencial. Configure Brave Search no painel de Integrações; não envie a chave no chat.',
  web_search_provider_unavailable:'O provedor de pesquisa não respondeu com sucesso. Nenhuma pesquisa foi confirmada.',
  skill_executor_unavailable:'Esta skill não tem executor compatível registrado. Ler a documentação não executa seu script.',
  material_changed_read_again:'O material mudou desde a leitura. Leia novamente e confira o SHA antes de editar.',
  material_type_read_only:'Este tipo de material usa um fluxo editorial próprio. O adapter atual edita fontes textuais file: vinculadas.',
  monthly_scheduler_not_supported:'O scheduler atual não executa rotinas mensais por esse adapter. Use uma agenda diária ou semanal compatível.',
  pipeline_rollout_not_configured:'O rollout ainda não foi ativado pelo operador. Faltam a configuração do executor e a verificação do ambiente protegido; YOLO não remove esse bloqueio.',
  pipeline_workflow_not_verified:'O workflow remoto difere da versão revisada pelo executor. A operação foi bloqueada.',
  pipeline_ci_not_verified:'Não há CI e build concluídos com sucesso para o SHA exato informado. O rollout foi bloqueado.',
  pipeline_production_review_not_configured:'A política do operador exige revisores configurados no ambiente production do GitHub.',
  adapter_resource_not_found:'O recurso não foi encontrado na área informada. Consulte o índice e use o identificador exato.',
  sensitive_adapter_input:'A solicitação contém um possível segredo. Configure credenciais pelo painel e remova valores sensíveis do conteúdo enviado ao adapter.',
  native_adapter_unavailable:'A API nativa do workspace não confirmou a operação. Consulte o estado antes de repetir uma alteração.',
  native_resource_conflict:'O recurso está ocupado ou mudou. Consulte o estado atual antes de preparar outra solicitação.',
}
async function call(path:string, body?:unknown, signal?:AbortSignal) {
  let response:Response
  try {response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'include',cache:'no-store',signal,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})}
  catch {throw new LiveRequestError('Não foi possível alcançar o servidor. Verifique a conexão e tente novamente.')}
  const data=await response.json().catch(()=>null)
  if(!response.ok)throw new LiveRequestError((typeof messages[data?.error]==='string'?messages[data?.error]:undefined)||(response.status===401?messages.unauthorized:response.status===404?'O endpoint Live não está disponível nesta versão do servidor.':'O servidor não liberou esta operação Live. Tente verificar o acesso novamente.'))
  return data
}
export async function loadManagedOptions(){
  const data=await call('/api/live/omni-context/options')
  if(data?.operationalSquadVersion!==1||!Array.isArray(data?.companies)||!Array.isArray(data?.agents)||typeof data?.consumptionApproved!=='boolean'||!data.companies.every((item:{id:number;name:string})=>item&&Number.isInteger(item.id)&&item.id>0&&typeof item.name==='string')||!data.agents.every((name:unknown)=>typeof name==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(name)))throw new LiveRequestError('A resposta de acesso Live não é compatível com esta interface.')
  return data
}
export async function prepareManagedContext(companyId:number,agentName:string):Promise<Context> {
  return call('/api/live/omni-context',{companyId,agentName})
}
export function createManagedContextTools(contextId:number) {
  let conversationId:string | null = null
  let binding:Promise<void> | null = null
  let closed = false
  return {
    // Supply from the SDK onConnect/conversation ID, never from tool parameters.
    onConversationConnected(id:string) {
      if (closed || conversationId) throw Error('Prepare uma nova sessão OmniNexus para esta conversa.')
      conversationId=id
      binding=call(`/api/live/omni-context/${contextId}/conversation`,{conversationId:id}).then(()=>{})
      return binding
    },
    disconnect() { closed=true },
    async approvals(approvalId?:string,decision?:'approve'|'reject'){
      if(closed||!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding
      return call(`/api/live/omni-context/${contextId}/approvals`,{conversationId,...(approvalId?{approvalId,decision}:{})})
    },
    async experience(action:string,parameters:Record<string,unknown>,requestId:string){
      if(closed||!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding;if(closed)throw Error('Conversa encerrada.')
      const result=await call(`/api/live/omni-context/${contextId}/experience`,{conversationId,action,parameters,requestId})
      if(closed)throw Error('Conversa encerrada.')
      return JSON.stringify(result)
    },
    async attach(file:File){
      if(closed||!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding
      const body=new FormData();body.set('conversationId',conversationId);body.set('file',file)
      const response=await fetch(`/api/live/omni-context/${contextId}/attachments`,{method:'POST',credentials:'include',body})
      if(!response.ok)throw Error('Não foi possível anexar este arquivo.')
      return response.json()
    },
    async recordToolAudit(toolCallId:string,toolName:string,stage:string,signal?:AbortSignal){
      if(!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding
      const response=await call(`/api/live/omni-context/${contextId}/tool-audit`,{conversationId,toolCallId,toolName,stage},signal)
      if(response?.recorded!==true)throw Error('Auditoria não confirmada.')
    },
    async runInternalTask(name:string,parameters:Record<string,unknown>,toolCallId:string) {
      if(closed||!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding
      if(closed)throw Error('Conversa encerrada.')
      if(!parameters||typeof parameters!=='object'||Array.isArray(parameters))throw Error('Parâmetros inválidos.')
      const valid=(value:unknown)=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(value)
      let suffix:string,body:Record<string,unknown>
      if(name==='request_internal_task'){
        if(Object.keys(parameters).sort().join(',')!=='operation,ticketId'||!valid(parameters.ticketId)||!['summarize_ticket','draft_ticket'].includes(String(parameters.operation))||!valid(toolCallId))throw Error('Pedido interno inválido.')
        suffix='tasks';body={ticketId:parameters.ticketId,operation:parameters.operation,requestId:toolCallId}
      }else if(name==='read_internal_task_status'||name==='cancel_internal_task'){
        if(Object.keys(parameters).join(',')!=='jobId'||!valid(parameters.jobId))throw Error('Tarefa inválida.')
        suffix=`tasks/${parameters.jobId}/${name==='cancel_internal_task'?'cancel':'status'}`;body={}
      }else throw Error('Ferramenta indisponível.')
      const result=await call(`/api/live/omni-context/${contextId}/${suffix}`,{conversationId,...body})
      if(closed)throw Error('Conversa encerrada.')
      return JSON.stringify(result)
    },
    clientTools: { search_omni_context:async (parameters:Record<string,unknown> = {}) => {
      if(!parameters||typeof parameters!=='object'||Array.isArray(parameters)||Object.keys(parameters).join(',')!=='query'||typeof parameters.query!=='string'||!parameters.query.trim()||parameters.query.trim().length>200)throw Error('Consulta inválida.')
      if(closed||!binding||!conversationId)throw Error('Conversa não vinculada.')
      await binding
      if(closed)throw Error('Conversa encerrada.')
      const result=await call(`/api/live/omni-context/${contextId}/query`,{conversationId,query:parameters.query.trim()})
      if(closed)throw Error('Conversa encerrada.')
      return JSON.stringify(result)
    }, read_current_omni_session:async (parameters:Record<string,unknown> = {}) => {
      if (Object.keys(parameters).length) throw Error('Esta ferramenta não aceita parâmetros.')
      if (closed || !binding || !conversationId) throw Error('Conversa ainda não vinculada ao OmniNexus.')
      await binding
      if (closed) throw Error('Conversa encerrada.')
      const result=await call(`/api/live/omni-context/${contextId}/read`,{conversationId})
      if (closed) throw Error('Conversa encerrada.')
      return JSON.stringify(result)
    } },
  }
}
export async function requestManagedSignedSession(contextId:number):Promise<{signedUrl:string;voiceId?:string;voiceName?:string}> {
  return call(`/api/live/omni-context/${contextId}/signed-session`,{})
}
