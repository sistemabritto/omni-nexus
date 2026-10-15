type SessionActions={
  snapshot:()=>{phase:string;companyId:number|null;continuity?:{writeStatus:string}}
  start:(companyId:number,company:string,agent:string,newConversation?:boolean)=>Promise<void>
  toggleMic:()=>Promise<void>;end:(status?:string)=>void;retryWrites:()=>Promise<void>|undefined
}
type Scope={companyId:number;company:string;agent:string}
// Presentation adapter only. In particular, start never chains a microphone action.
export function voiceFirstBindings(session:SessionActions,scope:Scope|null,allowNew:boolean){
  return {
    onStart:()=>{if(scope)void session.start(scope.companyId,scope.company,scope.agent)},
    onToggleMic:()=>{void session.toggleMic()},
    onEnd:()=>session.end('Áudio encerrado. Use Retomar conversa para continuar sem apagar o histórico.'),
    onRetrySave:()=>{void session.retryWrites()?.catch(()=>{})},
    onNew:allowNew&&scope?()=>{const state=session.snapshot();if(state.phase==='connecting'||['saving','error'].includes(state.continuity?.writeStatus||'')||(state.phase==='connected'&&state.companyId!==scope.companyId))return;if(state.phase==='connected')session.end();void session.start(scope.companyId,scope.company,scope.agent,true)}:undefined,
  }
}
export async function copyConversationText(text:string,clipboard?:Pick<Clipboard,'writeText'>){
  if(!clipboard)throw Error('Área de transferência indisponível.')
  await clipboard.writeText(text)
}
