// Actual TerminalServer HTTP handlers + SessionStore; no constructor/SDK turn or provider.
const path=require('node:path');
const {createRequire}=require('node:module');
const local=createRequire(path.resolve(__dirname,'../../dashboard/terminal-server/package.json'));
const {TerminalServer}=require('../../dashboard/terminal-server/src/server');
const SessionStore=require('../../dashboard/terminal-server/src/utils/session-store');
const runtime=Object.create(TerminalServer.prototype);
runtime.app=local('express')();runtime.baseFolder=process.cwd();runtime.claudeSessions=new Map();
runtime.webSocketConnections=new Map();runtime.globalSubscribers=new Set();
runtime.sessionStore=new SessionStore({storageDir:path.join(process.cwd(),'runtime-sessions')});
runtime.setupExpress();
const server=runtime.app.listen(0,'127.0.0.1',()=>process.stdout.write(JSON.stringify({port:server.address().port})+'\n'));
process.on('SIGTERM',async()=>{await runtime.saveSessionsToDisk();server.close(()=>process.exit(0));});
