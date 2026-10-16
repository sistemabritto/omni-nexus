import { useEffect, useRef, useState } from 'react'
import './VoicePicker.css'
type Voice={id:string;name:string;language:string;eligible:boolean;previewUrl:string|null}
type Catalog={voices:Voice[];hasMore:boolean;nextCursor:string|null;current:Voice;saved:Voice|null;overrideAllowed:boolean}
export default function VoicePicker({companyId,agentName,busy,connecting,activeVoice}:{companyId:number;agentName:string;busy:boolean;connecting:boolean;activeVoice:string}){
  const [data,setData]=useState<Catalog|null>(null),[voices,setVoices]=useState<Voice[]>([]),[choice,setChoice]=useState<string|null>(null)
  const [search,setSearch]=useState(''),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[notice,setNotice]=useState('')
  const abort=useRef(new AbortController()),audio=useRef<HTMLAudioElement>(null)
  useEffect(()=>{abort.current=new AbortController();const player=audio.current;return()=>{abort.current.abort();player?.pause()}},[])
  useEffect(()=>{if(busy)audio.current?.pause()},[busy])
  async function load(cursor?:string){
    setLoading(true);setNotice('')
    try{
      const query=new URLSearchParams({agentName});if(search.trim())query.set('search',search.trim());if(cursor)query.set('cursor',cursor)
      const response=await fetch(`/api/live/voices/${companyId}?${query}`,{credentials:'include',cache:'no-store',signal:abort.current.signal})
      if(!response.ok)throw Error()
      const result:Catalog=await response.json();if(abort.current.signal.aborted)return
      setData(result);setVoices(previous=>cursor?[...new Map([...previous,...result.voices].map(v=>[v.id,v])).values()]:result.voices)
      if(!cursor)setChoice(result.saved?.id||null)
    }catch{if(!abort.current.signal.aborted)setNotice('Catálogo indisponível. A configuração e as permissões da conta precisam ser verificadas; nenhuma voz foi alterada.')}
    finally{if(!abort.current.signal.aborted)setLoading(false)}
  }
  async function save(){
    setSaving(true);setNotice('')
    try{
      const response=await fetch(`/api/live/voices/${companyId}/preference`,{method:'PUT',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({voiceId:choice,agentName}),signal:abort.current.signal})
      if(!response.ok)throw Error()
      const result=await response.json();if(abort.current.signal.aborted)return
      setData(previous=>previous?{...previous,saved:result.saved,overrideAllowed:result.overrideAllowed}:previous)
      setNotice(result.saved&&!result.overrideAllowed?'Preferência salva, mas a troca por conversa ainda não está permitida no agente. Sua próxima conversa ficará bloqueada até essa permissão ou até restaurar a voz padrão.':busy?'Preferência salva para a próxima conversa. A chamada atual e seu histórico continuam; encerre quando quiser e inicie novamente.':'Preferência salva. A próxima conversa será iniciada com esta escolha.')
    }catch{if(!abort.current.signal.aborted)setNotice('Não foi possível salvar: voz indisponível, sem permissão ou incompatível com o modelo atual. A preferência anterior foi mantida.')}
    finally{if(!abort.current.signal.aborted)setSaving(false)}
  }
  function preview(voice:Voice){
    if(busy||!voice.previewUrl||!audio.current)return
    audio.current.src=voice.previewUrl
    void audio.current.play().catch(()=>setNotice('Prévia existente indisponível. Nenhum áudio novo foi gerado.'))
  }
  return <details className="live-voices" onToggle={e=>{if(e.currentTarget.open&&!data&&!loading)void load()}}>
    <summary>Voz e prévias existentes</summary>
    <div>
      <p>Ouça gravações já disponíveis na conta. Não gera áudio de teste e ouvir não salva uma escolha.</p>
      {data&&<dl><dt>Voz configurada no agente</dt><dd>{data.current.name}</dd><dt>Preferência salva nesta empresa</dt><dd>{data.saved?.name||'Usar a voz padrão do agente'}</dd>{busy&&<><dt>Voz solicitada na conversa atual</dt><dd>{activeVoice||'Voz padrão do agente'}</dd></>}</dl>}
      {data&&!data.overrideAllowed&&<p>A troca de voz por conversa não está habilitada no agente. Salvar uma preferência não habilita essa permissão.</p>}
      {busy&&<p>A conversa atual não será reiniciada. As prévias ficam pausadas durante a chamada; sua escolha vale para a próxima.</p>}
      <form onSubmit={e=>{e.preventDefault();void load()}}><label htmlFor="voice-search">Buscar vozes na conta</label><div className="voice-search"><input id="voice-search" value={search} onChange={e=>setSearch(e.target.value)} maxLength={100}/><button disabled={loading||saving}>Buscar</button></div></form>
      {data&&<fieldset disabled={saving||connecting}><legend>Escolha para a próxima conversa</legend><label className="voice-row"><input type="radio" name="live-voice" checked={choice===null} onChange={()=>setChoice(null)}/><span>Padrão do agente · {data.current.name}</span></label>{voices.map(v=><div key={v.id} className="voice-row"><label><input type="radio" name="live-voice" checked={choice===v.id} disabled={!v.eligible} onChange={()=>setChoice(v.id)}/><span>{v.name}{v.language?` · ${v.language}`:''}{!v.eligible?' · indisponível para este modelo/permissão':''}</span></label><button type="button" disabled={busy||!v.previewUrl||!v.eligible} aria-label={`Ouvir prévia de ${v.name}`} onClick={()=>preview(v)}>Ouvir prévia</button></div>)}</fieldset>}
      <audio ref={audio} controls={!busy} onError={()=>setNotice('Prévia existente indisponível. Nenhum áudio novo foi gerado.')} onPlay={()=>{if(busy)audio.current?.pause()}} preload="none" aria-label="Prévia existente da voz"/>
      {data&&<p>{voices.length} vozes carregadas nesta busca. {data.hasMore?'Há mais páginas disponíveis.':'Fim desta busca.'}</p>}
      {data?.hasMore&&<button type="button" disabled={loading||saving||!data.nextCursor} onClick={()=>void load(data.nextCursor||undefined)}>Carregar mais vozes</button>}
      {loading&&<p role="status">Consultando catálogo da conta…</p>}
      <p role="status" aria-live="polite">{notice}</p>
      <button type="button" className="voice-save" disabled={!data||loading||saving||connecting||choice===(data?.saved?.id||null)} onClick={()=>void save()}>{saving?'Salvando…':'Salvar escolha para próxima conversa'}</button>
    </div>
  </details>
}
