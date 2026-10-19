import { useEffect, useState } from 'react'
import { managedSession } from './managed-session'
type Pending={id:string;action:string;parameters:Record<string,unknown>}
export default function LiveApprovals({connected,companyId}:{connected:boolean;companyId:number|null}){
  const [items,setItems]=useState<Pending[]>([]),[busy,setBusy]=useState(''),[error,setError]=useState('')
  useEffect(()=>{
    if(!connected)return
    let active=true
    const load=()=>void managedSession.approvals().then(value=>{if(active)setItems(value.pending||[])}).catch(()=>{})
    load();const timer=setInterval(load,4000)
    return()=>{active=false;clearInterval(timer)}
  },[connected,companyId])
  async function decide(id:string,decision:'approve'|'reject'){
    setBusy(id);setError('')
    try{await managedSession.approvals(id,decision);setItems(current=>current.filter(item=>item.id!==id))}
    catch{setError('Não foi possível confirmar o resultado. Consulte o estado antes de repetir.')}
    finally{setBusy('')}
  }
  if(!connected)return null
  return <div aria-label="Solicitações para aprovação">{items.map(item=><section className="live-approval" key={item.id}><strong>Conferir solicitação · YOLO Mode desligado</strong><p>{item.action}</p><details><summary>Ver alterações</summary><pre>{JSON.stringify(item.parameters,null,2)}</pre></details><button disabled={!!busy} onClick={()=>void decide(item.id,'approve')}>{busy===item.id?'Aplicando…':'Aprovar'}</button><button disabled={!!busy} onClick={()=>void decide(item.id,'reject')}>Recusar</button></section>)}{error&&<p role="alert" className="live-inline-notice">{error}</p>}</div>
}
