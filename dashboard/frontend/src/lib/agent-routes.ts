// Public names can evolve without changing persisted agent/session identifiers.
export const agentIdentities:Record<string,{name:string;route:string;color:string}>={
  'clawdia-assistant':{name:'Hera',route:'hera',color:'#a3ff12'},
  'mako-marketing':{name:'Orion',route:'orion',color:'#5ddcff'},
  'pixel-social-media':{name:'Dante',route:'dante',color:'#f9a66c'},
  'canvas-designer':{name:'Íris',route:'iris',color:'#dca1ff'},
  'bolt-executor':{name:'Vulcano',route:'vulcano',color:'#ff866c'},
  'oath-verifier':{name:'Argos',route:'argos',color:'#78eed0'},
  'atlas-project':{name:'Atlas',route:'atlas',color:'#8bb8ff'},
  'sage-strategy':{name:'Sage',route:'sage',color:'#b9a3ff'},
  'raven-critic':{name:'Raven',route:'raven',color:'#e4a6e8'},
  'hawk-debugger':{name:'Hawk',route:'hawk',color:'#ffc673'},
  'lens-reviewer':{name:'Lens',route:'lens',color:'#86d8e7'},
  'probe-qa':{name:'Probe',route:'probe',color:'#b3e0aa'},
}
export const retiredAgents:Record<string,string>={"apex-architect":"bolt-executor","aria-hr":"clawdia-assistant","compass-planner":"atlas-project","dex-data":"sage-strategy","echo-analyst":"sage-strategy","flow-git":"bolt-executor","flux-finance":"sage-strategy","goal-planner":"atlas-project","goal-suggester":"atlas-project","grid-tester":"probe-qa","helm-conductor":"atlas-project","kai-personal-assistant":"clawdia-assistant","lex-legal":"oath-verifier","lumen-learning":"sage-strategy","mentor-courses":"pixel-social-media","mirror-retro":"raven-critic","nex-sales":"mako-marketing","nova-product":"mako-marketing","oracle":"clawdia-assistant","plugin-reach-reach":"pixel-social-media","prism-scientist":"sage-strategy","project-planner":"atlas-project","pulse-community":"pixel-social-media","quill-writer":"pixel-social-media","reels-copilot":"pixel-social-media","scout-explorer":"hawk-debugger","scroll-docs":"sage-strategy","trail-tracer":"hawk-debugger","vault-security":"oath-verifier","zara-cs":"clawdia-assistant","zen-simplifier":"bolt-executor"}
export const agentSlug=(value:string)=>Object.keys(agentIdentities).find(slug=>agentIdentities[slug].route===value)||retiredAgents[value]||value
export const agentHref=(slug:string)=>`/agents/${agentIdentities[agentSlug(slug)]?.route||encodeURIComponent(slug)}`
export const agentIdentity=(slug:string)=>agentIdentities[agentSlug(slug)]||{name:slug,route:slug,color:'#a3ff12'}
