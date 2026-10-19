import type { ReactNode } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { agentHref, agentSlug } from '../lib/agent-routes'
export default function AgentRoute({children}:{children:ReactNode}){
  const {name=''}=useParams(),location=useLocation(),canonical=agentHref(agentSlug(name))
  const suffix=location.pathname.endsWith('/voice')?'/voice':''
  return location.pathname!==canonical+suffix?<Navigate replace to={canonical+suffix+location.search+location.hash}/>:children
}
