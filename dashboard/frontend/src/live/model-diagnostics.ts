// Contract v1: metadata only. Never selects a model or changes provider policy.
export type ModelDiagnostics = {
  configuredModel: string | null; activeModel: string | null; attemptingModel: string | null
  fallbackModels: string[]; fallbackBlockedModels: string[]; attempt: number | null; maxAttempts: number | null
  contextReset: boolean; loaded: boolean; unavailable: boolean; events: string[]
}
export const initialDiagnostics: ModelDiagnostics = { configuredModel:null, activeModel:null, attemptingModel:null, fallbackModels:[], fallbackBlockedModels:[], attempt:null, maxAttempts:null, contextReset:false, loaded:false, unavailable:false, events:[] }
const model = (value: unknown) => typeof value === 'string' && /^[a-zA-Z0-9._-]{1,100}$/.test(value) ? value : null
const count = (value: unknown) => Number.isInteger(value) && Number(value) > 0 && Number(value) <= 2 ? Number(value) : null
const models = (value: unknown) => Array.isArray(value) ? value.map(model).filter((x): x is string => x !== null).slice(0,10) : []
export function reasonLabel(value: unknown) {
  return ({initial:'início da sessão',model_unavailable:'modelo indisponível',go_away:'servidor solicitou nova sessão',network_error:'conexão perdida'} as Record<string,string>)[String(value)] || 'motivo não informado'
}
export function liveErrorMessage(value: unknown) {
  return ({provider_auth_failed:'Autenticação do provedor recusada.',provider_quota_exhausted:'Cota do provedor esgotada. Nenhuma troca automática será feita.',provider_rate_limited:'Limite de requisições do provedor atingido. Nenhuma troca automática será feita.',provider_network_error:'Falha de rede com o provedor.',provider_model_unavailable:'Modelo indisponível após as tentativas permitidas.',provider_unavailable:'Provedor indisponível.',live_disabled:'Live desabilitado no servidor.',session_limit:'Limite desta sessão atingido.',setup_timeout:'Tempo de conexão esgotado.',audio_rate_limit:'Limite de envio de áudio atingido.',invalid_audio_or_provider_protocol:'Falha no protocolo da sessão.',session_rate_limit:'Limite de sessões atingido.'} as Record<string,string>)[String(value)] || 'Sessão indisponível. Verifique a configuração do servidor.'
}
type Action = {type:'config'|'event'; value:Record<string,unknown>} | {type:'stop'|'reset'|'unavailable'}
export function modelDiagnostics(state: ModelDiagnostics, action: Action): ModelDiagnostics {
  if(action.type==='stop')return {...state,activeModel:null,attemptingModel:null}
  if(action.type==='reset')return {...state,activeModel:null,attemptingModel:null,attempt:null,contextReset:false,events:[]}
  if(action.type==='unavailable')return {...state,unavailable:true}
  const input = 'value' in action ? action.value : {}
  const value=input && typeof input==='object' && !Array.isArray(input) ? input : {}
  if(action.type==='config')return {...state,loaded:true,unavailable:false,configuredModel:model(value.configuredModel),fallbackModels:models(value.fallbackModels),fallbackBlockedModels:models(value.fallbackBlockedModels),maxAttempts:count(value.maxProviderAttempts)} // HTTP activeModel is never session evidence.
  let next={...state};let entry=''
  if(value.event==='model_attempt' && !state.activeModel){next={...next,configuredModel:model(value.configuredModel) || state.configuredModel,attemptingModel:model(value.model),attempt:count(value.attempt),maxAttempts:count(value.maxAttempts)};entry=`Tentativa ${next.attempt ?? '?'}: ${next.attemptingModel ?? 'modelo não informado'} · ${reasonLabel(value.reason)}`}
  if(value.event==='model_switch' && !state.activeModel){next={...next,attemptingModel:model(value.toModel),attempt:count(value.attempt),maxAttempts:count(value.maxAttempts)};entry=`Troca antes de conectar: ${model(value.fromModel) ?? '?'} → ${model(value.toModel) ?? '?'} · ${reasonLabel(value.reason)}`}
  if(value.event==='model_active' && model(value.activeModel)){next={...next,activeModel:model(value.activeModel),attemptingModel:null,attempt:count(value.attempt)};entry=`Modelo ativo confirmado: ${next.activeModel}`}
  if(value.status==='reconnect_required'){next={...next,activeModel:null,attemptingModel:null};entry=`Nova sessão necessária · ${reasonLabel(value.reason)}`}
  if(value.error)entry=liveErrorMessage(value.error)
  if(value.contextPreserved===false)next.contextReset=true
  return {...next,events:entry?[...state.events,entry].slice(-8):state.events}
}
