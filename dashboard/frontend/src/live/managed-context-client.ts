// Client-tool glue only: no SDK import, token request, microphone or provider activation.
type Context = { contextId:number; runtimeSessionId:string; company:{id:number;name:string}; agentName:string }
async function call(path:string, body:unknown) {
  const response = await fetch(path,{method:'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  if (!response.ok) throw Error('Não foi possível consultar o contexto autorizado do OmniNexus.')
  return response.json()
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
export async function requestManagedSignedSession(contextId:number):Promise<{signedUrl:string;voiceId?:string;voiceName?:string}> {
  return call(`/api/live/omni-context/${contextId}/signed-session`,{})
}
