// Local QA identity and empty states; never shared with production or persisted server-side.
module.exports=async function fixture(page,role='admin') {
 await page.routeWebSocket('**',ws=>ws.close());
 await page.addInitScript(()=>{localStorage.setItem('evo:active_company','1');localStorage.setItem('evo_lang','pt-BR')});
 await page.route('**/api/**',async route=>{
 const u=new URL(route.request().url()),p=u.pathname.replace(/^\/terminal/,'');let data;let status=200;
 if(p==='/api/auth/needs-setup')data={needs_setup:false};
 else if(p==='/api/auth/me'){if(role==='anonymous')return route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:'QA não autenticado'})});data={user:{id:1,username:'QA local',display_name:'Revisão local',role,onboarding_state:'completed'},permissions:role==='admin'?{}:{agents:{view:true},workspace:{view:true}}};}
 else if(p==='/api/settings/workspace')data={workspace:{name:'Workspace QA',language:'pt-BR'}};
 else if(p==='/api/companies')data=[{id:1,name:'Empresa Alfa · QA',slug:'qa-alfa',status:'active',logo_url:'/favicon.png'},{id:2,name:'Empresa Beta · QA',slug:'qa-beta',status:'active'}];
 else if(p==='/api/agents')data=[{name:'qa-agent',description:'Agente somente de teste',model:'QA',memory_count:0,custom:true,skills:[],tools:[],layer:'business'}];
 else if(p==='/api/agents/active')data={active_agents:[]};
 else if(p==='/api/orchestration-jobs')data={jobs:[]};
 else if(p.includes('/sessions/by-agent/'))data={sessions:[]};
 else if(p==='/api/memory')data={global_files:[],agent_memory_counts:{}};
 else if(['/api/users','/api/roles','/api/services','/api/scheduler','/api/templates','/api/systems','/api/plugins','/api/plugins/marketplace','/api/routines','/api/skills'].includes(p))data=[];
 else if(p==='/api/heartbeats')data={heartbeats:[]};else if(p==='/api/triggers')data={triggers:[],total:0};
 else if(p==='/api/tasks')data={tasks:[]};else if(p==='/api/tickets')data={tickets:[],total:0};else if(p==='/api/tickets/counts')data={total:0,counts:{}};
 else if(p==='/api/shares')data={shares:[]};else if(p==='/api/config/env')data={entries:[]};else if(p==='/api/integrations')data={integrations:[]};else if(p==='/api/social-accounts')data={platforms:[]};
 else if(p==='/api/media/jobs')data={jobs:[],total:0};else if(p==='/api/audit')data={entries:[],total:0,page:1,pages:0};
 else if(p==='/api/knowledge/connections')data={connections:[]};
 else if(p==='/api/version/check')data={current:'QA'};
 else if(p==='/api/docs')data=[];
 else if(p.startsWith('/api/shares/'))data={type:'markdown',content:'Artefato de teste local. Não é um compartilhamento real.'};
 else {status=503;data={error:'Serviço indisponível no fixture local de QA'};}
 await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 });
};
