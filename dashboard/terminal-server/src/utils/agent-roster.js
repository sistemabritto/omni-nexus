const fs = require('node:fs');
const path = require('node:path');
// Historical session IDs remain valid; retired roles are playbooks, not catalog agents.
function resolveAgentFile(root,cwd,agent){
  if(typeof agent!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(agent))throw Error('Invalid agent identifier');
  const normal=path.join(root,'.claude','agents',`${agent}.md`);
  const manifest=path.join(root,'scripts','squad-retirements.json');
  const target=fs.existsSync(manifest)?JSON.parse(fs.readFileSync(manifest,'utf8')).agents?.[agent]:null;
  if(target){
    const reference=path.join(root,'.claude','skills','squad-role-library','references',`${agent}.md`);
    if(fs.existsSync(reference))return reference;
    if(!fs.existsSync(normal))return path.join(root,'.claude','agents',`${target}.md`);
  }
  return fs.existsSync(normal)?normal:path.join(cwd,'.claude','agents',`${agent}.md`);
}

module.exports = { resolveAgentFile };
