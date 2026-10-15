// Client-tool glue only: no SDK import, token request, microphone or provider activation.
type Context = { contextId:number; runtimeSessionId:string; company:{id:number;name:string}; agentName:string }
export class LiveRequestError extends Error {
  constructor(message:string){super(message);this.name='LiveRequestError'}
}
const messages:Record<string,string>={
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
  origin_forbidden:'A origem desta solicitação não foi aceita pelo servidor.',
}
async function call(path:string, body?:unknown) {
  let response:Response
  try {response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)})}
  catch {throw new LiveRequestError('Não foi possível alcançar o servidor. Verifique a conexão e tente novamente.')}
  const data=await response.json().catch(()=>null)
  if(!response.ok)throw new LiveRequestError((typeof messages[data?.error]==='string'?messages[data?.error]:undefined)||(response.status===401?messages.unauthorized:response.status===404?'O endpoint Live não está disponível nesta versão do servidor.':'O servidor não liberou esta operação Live. Tente verificar o acesso novamente.'))
  return data
}
export async function loadManagedOptions(){
  const data=await call('/api/live/omni-context/options')
  if(!Array.isArray(data?.companies)||!Array.isArray(data?.agents)||typeof data?.consumptionApproved!=='boolean'||!data.companies.every((item:{id:number;name:string})=>item&&Number.isInteger(item.id)&&item.id>0&&typeof item.name==='string')||!data.agents.every((name:unknown)=>typeof name==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(name)))throw new LiveRequestError('A resposta de acesso Live não é compatível com esta interface.')
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
    clientTools: { read_current_omni_session:async (parameters:Record<string,unknown> = {}) => {
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
export async function requestManagedSignedSession(contextId:number):Promise<{signedUrl:string}> {
  return call(`/api/live/omni-context/${contextId}/signed-session`,{})
}
