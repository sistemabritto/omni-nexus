'use strict';
const crypto = require('node:crypto');
// Only server code can attach this value. JSON/browser keys cannot represent it.
const OWNED_READ_CONNECTION = Symbol('owned-read-connection');
const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const deny = () => Object.assign(new Error('owned_read_context_required'), {code:'owned_read_context_required'});
function requestBackend(url,options) {
  return new Promise((resolve,reject)=>{
    const protocol=require(url.protocol==='https:'?'node:https':'node:http');
    const req=protocol.request(url,{method:options.method,headers:options.headers},response=>{
      let bytes=0,body='';response.setEncoding('utf8');
      response.on('data',chunk=>{bytes+=Buffer.byteLength(chunk);if(bytes>100000){req.destroy();reject(deny());}else body+=chunk;});
      response.on('end',()=>resolve({ok:response.statusCode===200,text:async()=>body}));
      response.on('error',()=>reject(deny()));
    });
    req.setTimeout(10000,()=>req.destroy());req.on('error',()=>reject(deny()));req.end(options.body);
  });
}
function createOwnedReadResolver({backendBase, publicOrigin, fetchImpl=requestBackend}) {
  const base=new URL(backendBase), origin=new URL(publicOrigin);
  if(origin.origin!==publicOrigin||!(['https:','http:'].includes(origin.protocol)))throw deny();
  if (!['http:','https:'].includes(base.protocol)||base.username||base.password||base.search||base.hash||base.pathname!=='/') throw deny();
  const resolve = async (sessionId, query, connection) => {
    if (!connection?.cookie || connection.origin!==publicOrigin || !connection.active()) throw deny();
    const load=async()=>{
      if (!connection.active()) throw deny();
      const response=await fetchImpl(new URL('/api/live/omni-context/runtime-read',base),{
        method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),
        headers:{'Content-Type':'application/json',Cookie:connection.cookie,Origin:connection.origin,Host:origin.host},
        body:JSON.stringify({runtimeSessionId:sessionId,agentName:connection.agentName,query})});
      if (!response.ok || !connection.active()) throw deny();
      const raw=await response.text();if(Buffer.byteLength(raw)>100000)throw deny();
      const packet=JSON.parse(raw);
      if(packet.sessionId!==sessionId||packet.agentName!==connection.agentName||(query!==undefined&&!Array.isArray(packet.documents)))throw deny();
      return packet;
    };
    const packet=await load(), revision=digest(packet);
    if(query===undefined)return packet;
    return {...packet,revision,verify:async()=>{try{return connection.active() && digest(await load())===revision;}catch{return false;}}};
  };
  resolve.authorize=(sessionId,connection)=>resolve(sessionId,undefined,connection);
  return resolve;
}
module.exports={createOwnedReadResolver,OWNED_READ_CONNECTION};
