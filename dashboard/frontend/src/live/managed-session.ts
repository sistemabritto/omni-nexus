// One authenticated connection survives SPA navigation. No provider or microphone on import.
import { createManagedContextTools, prepareManagedContext, requestManagedSignedSession } from './managed-context-client'
import { encodePCM, Playback } from './audio'
type Connection = import('@elevenlabs/client').WebSocketConnection
type Message = {author:string;text:string}
type State = {phase:'idle'|'connecting'|'connected';status:string;mic:boolean;companyId:number|null;contextChanged:boolean;company:string;agent:string;messages:Message[];runtimeSessionId:string;voiceName:string}
const initial:State={phase:'idle',status:'Selecione empresa e agente. Microfone desligado.',mic:false,companyId:null,contextChanged:false,company:'',agent:'',messages:[],runtimeSessionId:'',voiceName:''}
export class ManagedSession {
  private state:State={...initial}; private listeners=new Set<()=>void>(); private connection:Connection|null=null
  private tools:ReturnType<typeof createManagedContextTools>|null=null; private generation=0; private micStarting=false
  private stream:MediaStream|null=null; private audio:AudioContext|null=null; private processor:ScriptProcessorNode|null=null; private playback:Playback|null=null
  private connect:(signedUrl:string,voiceId?:string)=>Promise<Connection>
  constructor(connect=async(signedUrl:string,voiceId?:string)=>{const sdk=await import('@elevenlabs/client');return sdk.WebSocketConnection.create({signedUrl,connectionType:'websocket',textOnly:false,...(voiceId?{overrides:{tts:{voiceId}}}:{})})}){this.connect=connect}
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener)}}
  snapshot=()=>this.state
  private patch(value:Partial<State>){this.state={...this.state,...value};this.listeners.forEach(listener=>listener())}
  private message(author:string,text:string){this.patch({messages:[...this.state.messages,{author,text}]})}
  async start(companyId:number,company:string,agent:string){
    if(this.state.phase!=='idle')return
    const generation=++this.generation;this.patch({phase:'connecting',status:'Preparando sessão autorizada…',companyId,contextChanged:false,company,agent,messages:[],runtimeSessionId:'',voiceName:''})
    try {
      const context=await prepareManagedContext(companyId,agent);if(generation!==this.generation)return
      const signed=await requestManagedSignedSession(context.contextId);if(generation!==this.generation)return
      const tools=createManagedContextTools(context.contextId);this.tools=tools
      const connection=await this.connect(signed.signedUrl,signed.voiceId)
      if(generation!==this.generation){connection.close();return}
      this.connection=connection
      connection.addListener(event=>{if(generation===this.generation && this.state.mic)this.playback?.play(event.audio_base_64)})
      connection.onDisconnect(()=>{if(generation===this.generation)this.end('Conexão encerrada. Inicie novamente por um novo clique.')})
      const binding=tools.onConversationConnected(connection.conversationId)
      // Register before awaiting binding: the SDK queues initial events until this callback.
      connection.onMessage(event=>{if(generation!==this.generation)return
        if(event.type==='ping')connection.sendMessage({type:'pong',event_id:event.ping_event.event_id})
        if(event.type==='agent_response')this.message('Nexus Live',event.agent_response_event.agent_response)
        if(event.type==='user_transcript')this.message('Você · voz',event.user_transcription_event.user_transcript)
        if(event.type==='interruption')this.playback?.stop()
        if(event.type==='error')this.end('Falha na conversa. Microfone desligado.')
        if(event.type==='client_tool_call'){
          const call=event.client_tool_call
          void (async()=>{try {
            if(call.tool_name!=='read_current_omni_session')throw Error('Ferramenta indisponível.')
            const result=await tools.clientTools.read_current_omni_session(call.parameters)
            if(generation===this.generation)connection.sendMessage({type:'client_tool_result',tool_call_id:call.tool_call_id,result,is_error:false})
          }catch{if(generation===this.generation)connection.sendMessage({type:'client_tool_result',tool_call_id:call.tool_call_id,result:'Contexto indisponível ou não autorizado.',is_error:true})}})()
        }
      })
      await binding
      if(generation!==this.generation)return
      this.patch({phase:'connected',runtimeSessionId:context.runtimeSessionId,voiceName:signed.voiceName||'Voz padrão do agente',status:'Conectado por texto. Ative o microfone quando quiser falar.'})
    } catch {if(generation===this.generation)this.end('Não foi possível iniciar. Verifique acesso e configuração do servidor.')}
  }
  syncCompany(companyId:number|null){
    if(this.state.companyId===null || this.state.companyId===companyId)return
    this.end()
    this.patch({...initial,messages:[],contextChanged:true,status:'Empresa alterada no menu global. A conversa anterior foi encerrada e o microfone desligado. Inicie uma nova conversa para usar a empresa atual.'})
  }
  send(text:string){if(this.state.phase!=='connected' || !text.trim())return;this.connection?.sendMessage({type:'user_message',text:text.trim()});this.message('Você · texto',text.trim())}
  async toggleMic(){
    if(this.state.mic){this.stopMic();this.patch({status:'Microfone desligado. Continue por texto na mesma conversa.'});return}
    const connection=this.connection,generation=this.generation
    if(!connection || this.state.phase!=='connected' || this.micStarting)return
    this.micStarting=true
    try {
      if(connection.inputFormat.format!=='pcm' || connection.outputFormat.format!=='pcm')throw Error('Formato de áudio não disponível.')
      const stream=await navigator.mediaDevices.getUserMedia({audio:true})
      if(generation!==this.generation){stream.getTracks().forEach(track=>track.stop());return}
      this.stream=stream;const audio=new AudioContext({sampleRate:connection.inputFormat.sampleRate});this.audio=audio
      await audio.resume();if(generation!==this.generation){this.stopMic();return}
      this.playback=new Playback(audio,connection.outputFormat.sampleRate)
      const source=audio.createMediaStreamSource(stream),processor=audio.createScriptProcessor(2048,1,1);this.processor=processor
      processor.onaudioprocess=event=>{if(this.state.mic && generation===this.generation)connection.sendMessage({user_audio_chunk:encodePCM(event.inputBuffer.getChannelData(0))})}
      source.connect(processor);processor.connect(audio.destination)
      this.patch({mic:true,status:'Microfone ativo. Texto e voz usam esta mesma conversa.'})
    }catch{this.stopMic();if(generation===this.generation)this.patch({status:'Microfone indisponível. Continue por texto na mesma conversa.'})}finally{this.micStarting=false}
  }
  private stopMic(){this.stream?.getTracks().forEach(track=>track.stop());this.stream=null;this.processor?.disconnect();this.processor=null;this.playback?.stop();this.playback=null;void this.audio?.close();this.audio=null;this.patch({mic:false})}
  end(status='Conversa encerrada. Microfone desligado.') {this.generation++;this.tools?.disconnect();this.tools=null;const connection=this.connection;this.connection=null;this.stopMic();connection?.close();this.patch({phase:'idle',status})}
  reset(){this.end();this.patch({...initial,messages:[]})}
}
export const managedSession=new ManagedSession()
