import { useEffect, useRef, useState } from 'react'
import './LiveFileSources.css'
type Preview={path:string;sha256:string;size:number;companyId:number;expectedRevision:number}
type Binding={id:string;revision:number;path?:string;status:'current'|'changed_rebind_required'|'unavailable'}
export default function LiveFileSources({companyId,company}:{companyId:number;company:string}){
  const [path,setPath]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[confirmed,setConfirmed]=useState(false)
  const [bindings,setBindings]=useState<Binding[]>([]),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
  const abort=useRef(new AbortController())
  useEffect(()=>{abort.current=new AbortController();return()=>abort.current.abort()},[])
  async function call(action:string,body:unknown={}){
    const response=await fetch(`/api/live/file-sources/${companyId}/${action}`,{method:'POST',credentials:'include',cache:'no-store',signal:abort.current.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    const data=await response.json().catch(()=>null)
    if(!response.ok)throw Error(response.status===409?'O arquivo ou vínculo mudou. Confira novamente antes de confirmar.':response.status===403?'Arquivo indisponível para este acesso. Confira a pasta, o formato e as permissões.':'Operação indisponível. Confira os vínculos antes de tentar novamente.')
    return data
  }
  async function refresh(){const data=await call('list');if(!abort.current.signal.aborted)setBindings(data.bindings)}
  async function run(action:()=>Promise<void>){setBusy(true);setNotice('');try{await action()}catch(error){if(!abort.current.signal.aborted)setNotice(error instanceof Error?error.message:'Operação indisponível.')}finally{if(!abort.current.signal.aborted)setBusy(false)}}
  async function inspect(){setPreview(null);setConfirmed(false);const data:Preview=await call('preview',{path:path.trim()});if(data.companyId!==companyId)throw Error('A empresa retornada não corresponde à seleção. Confira novamente.');if(!abort.current.signal.aborted){setPreview(data);setNotice('Arquivo conferido. Confirme a empresa antes de vincular.')}}
  async function bind(){
    if(!preview||!confirmed||preview.companyId!==companyId)return
    await call('bind',{path:preview.path,sha256:preview.sha256,expectedRevision:preview.expectedRevision,confirmOwnership:true})
    if(abort.current.signal.aborted)return
    setPreview(null);setConfirmed(false);setNotice('Arquivo vinculado às suas consultas nesta empresa.');await refresh()
  }
  async function revoke(binding:Binding){await call('revoke',{id:binding.id,expectedRevision:binding.revision});if(abort.current.signal.aborted)return;setNotice('Vínculo removido das próximas consultas. O arquivo foi preservado.');await refresh()}
  return <details className="live-file-sources" onToggle={e=>{if(e.currentTarget.open)void run(refresh)}}>
    <summary>Arquivos para consultar · {company}</summary>
    <div className="live-file-body">
      <p>Vincule um arquivo já acessível no Workspace a esta empresa. Uma alteração no conteúdo exige nova conferência. Nenhuma chamada de voz é necessária.</p>
      <form onSubmit={e=>{e.preventDefault();void run(inspect)}}>
        <label htmlFor="live-file-path">Caminho do arquivo no Workspace</label>
        <input id="live-file-path" value={path} onChange={e=>{setPath(e.target.value);setPreview(null);setConfirmed(false);setNotice('')}} placeholder="workspace/pasta/roteiro.md" disabled={busy} autoComplete="off" spellCheck={false} aria-describedby="live-file-help"/>
        <small id="live-file-help">Formatos: .md, .txt e .html; até 128 KiB. Padrões conhecidos de credenciais e links simbólicos são recusados.</small>
        <button type="submit" disabled={busy||!path.trim()}>Conferir arquivo</button>
      </form>
      {preview&&<div className="live-file-confirm">
        <p>{preview.path} · {preview.size} bytes</p>
        <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>Confirmo que este arquivo pertence a {company} e pode compor minhas consultas nesta empresa.</label>
        <button type="button" disabled={busy||!confirmed} onClick={()=>void run(bind)}>Vincular arquivo a {company}</button>
      </div>}
      <p role="status" aria-live="polite">{busy?'Conferindo fontes…':notice}</p>
      <ul>{bindings.map(binding=><li key={binding.id}>
        <span>{binding.path||'Arquivo indisponível'} — {binding.status==='current'?'Vínculo atual':binding.status==='changed_rebind_required'?'Conteúdo mudou; conferir novamente':'Sem acesso ou conteúdo indisponível'}</span>
        <button type="button" disabled={busy} onClick={()=>void run(()=>revoke(binding))}>Remover vínculo</button>
      </li>)}</ul>
      {!bindings.length&&!busy&&<p>Nenhum arquivo vinculado às suas consultas nesta empresa.</p>}
    </div>
  </details>
}
