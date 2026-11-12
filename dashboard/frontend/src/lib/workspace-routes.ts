// Display metadata only; authorization remains in App routes and backend.
export const workspaceAreas = [
  ['/live', 'Live', 'Conversa por voz'],
  ['/', 'Conversa central', 'Conversa, autoria e sessões'], ['/omninexus', 'Conversa central', 'Conversa, autoria e sessões'],
  ['/overview', 'Painel operacional', 'Visão geral da operação'], ['/agents', 'Squad de agentes', 'Responsáveis e conversas por agente'],
  ['/missions', 'Projetos e missões', 'Objetivos, projetos e entregas'], ['/kanban', 'Quadro de trabalho', 'Tickets e revisão'],
  ['/workspace', 'Materiais', 'Arquivos e artefatos'], ['/orquestracao', 'Jobs e bloqueios', 'Execução e estados reportados'],
  ['/tasks', 'Tarefas', 'Trabalho agendado e em andamento'], ['/activity', 'Atividade', 'Histórico operacional'],
  ['/scheduler', 'Agenda', 'Agendamentos da operação'], ['/routines', 'Rotinas', 'Processos recorrentes'],
  ['/heartbeats', 'Heartbeats', 'Rotinas dos agentes'], ['/triggers', 'Gatilhos', 'Eventos e automações'], ['/media', 'Conteúdo e mídia', 'Produção de artefatos'],
  ['/memory', 'Memória e fontes', 'Arquivos de memória disponíveis'], ['/mempalace', 'Palácio de memória', 'Organização do conhecimento'],
  ['/knowledge', 'Conhecimento', 'Conexões, fontes e pesquisa'], ['/skills', 'Skills', 'Capacidades instaladas'],
  ['/inteligencia', 'Integrações', 'Conectores e serviços'], ['/integrations', 'Integrações', 'Conectores e serviços'],
  ['/providers', 'Provedores', 'Modelos e conexões'], ['/mcp-servers', 'Servidores MCP', 'Ferramentas e conexões'],
  ['/plugins', 'Plugins', 'Extensões da operação'], ['/plugins-ui', 'Extensão', 'Interface fornecida pelo plugin'],
  ['/templates', 'Templates', 'Modelos de trabalho'], ['/systems', 'Sistemas', 'Serviços disponíveis'],
  ['/settings', 'Configurações', 'Preferências e administração'], ['/users', 'Usuários', 'Acesso ao workspace'],
  ['/roles', 'Papéis e permissões', 'Regras de acesso'], ['/audit', 'Auditoria', 'Registro de alterações'],
  ['/backups', 'Backups', 'Cópias e restauração'], ['/shares', 'Compartilhamentos', 'Links e acesso aos artefatos'],
  ['/costs', 'Custos', 'Uso e consumo'], ['/topics', 'Pautas', 'Discussões e tickets'], ['/tickets', 'Ticket', 'Autoria, estado e histórico'],
] as const
export function getWorkspaceArea(path: string) {
  return [...workspaceAreas].sort((a,b) => b[0].length-a[0].length).find(([prefix]) => path === prefix || (prefix !== '/' && path.startsWith(`${prefix}/`))) || ['/', 'Workspace', 'OmniNexus Live']
}
