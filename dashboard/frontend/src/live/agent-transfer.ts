import { agentIdentities } from '../lib/agent-routes'
const fold=(text:string)=>text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()
export function requestedAgent(text:string):string|null{
  const value=fold(text)
  for(const [slug,identity] of Object.entries(agentIdentities)){
    const name=fold(identity.name)
    const match=new RegExp(`(?:quero (?:falar|conversar) com|(?:chame|chama|chamar)|(?:passe|passa|troque|troca)(?: a conversa)? (?:para|pro|pra))\\s+(?:o |a )?${name}\\b`).exec(value)
    if(match&&!/\bnao\s*$/.test(value.slice(Math.max(0,match.index-12),match.index)))return slug
  }
  return null
}
