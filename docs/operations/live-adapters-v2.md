# Live: transferência, GitHub e adapters V2

## Problemas corrigidos

1. Durante o handoff, uma transcrição podia iniciar uma gravação enquanto o
   destino era preparado. O cliente encerrava a origem e `start()` recusava a
   nova conexão porque a continuidade ainda estava em `saving`. A entrada da
   origem agora é pausada depois do preparo, a gravação final é confirmada e
   só então a conexão é trocada. Falha nessa confirmação preserva a origem.
   Há etapas de diagnóstico sem texto/áudio/credenciais na auditoria.
2. O proprietário GitHub autorizado é `sistemabritto`. A grafia
   `sistema-britto` pode ser resolvida pela lista explícita `ownerAliases` da
   política; ela nunca concede acesso a outra conta. O catálogo inicial usa
   agora o usuário e a empresa do contexto ao informar o estado da integração.
3. Respostas GitHub grandes têm páginas de transporte com `nextOffset` e
   hash, antes de `nextPage`. Não são silenciosamente truncadas nem convertidas
   em um erro genérico de autorização. Falhas têm códigos estáticos distintos.

## Adapters

`operate_omni_adapter` despacha operações nomeadas, nunca shell ou URL livre.
O contrato completo e exemplos estão em `.claude/skills/live-adapters/SKILL.md`.

- Heartbeats: criar desativado, ajustar campos permitidos e configurar alertas
  por categoria, cooldown e horário de silêncio no transporte existente.
- Rotinas: criar desativada e alterar agendas diária/semanal de executores
  registrados. Recarga não confirmada permanece pendente. Mensal retorna
  bloqueio explícito porque o scheduler atual não o executa por este caminho.
- Gatilhos: criar desativado e alterar filtros/condições limitados, sem eval.
  Só executores registrados podem ser selecionados; segredos de webhook não
  são retornados ao agente.
- Integrações: criar/editar metadados customizados, orientar configuração no
  painel e testar saúde. Valores de credenciais não são aceitos pelo adapter.
  Metadados não criam um cliente de API executável.
- Materiais: editar fonte textual `file:` vinculada ao usuário/empresa, com
  hash esperado, backup, revisão e registro de autoria da edição. Roteiros de
  Gravações mantêm o fluxo editorial próprio.
- Skills: executar bindings específicos já implementados de referência de
  marca, com recibo. Não há executor genérico de comandos de SKILL.md.
- Internet: plugin Brave Search configurável no painel; consulta fixa, fontes,
  data e filtro de links locais/privados. Não navega nos resultados com cookies
  internos. Sem chave, informa bloqueio de configuração.
- Remoção: adapter separado para automações e integrações customizadas, com
  aprovação específica e snapshot criptografado antes do efeito. GitHub não
  oferece exclusão de arquivos, repositórios ou branches.
- GitHub: jobs de commit de vários arquivos em branch de trabalho, CI de
  workflow registrado e rollout protegido; sem force push nem autoaprovação.

## Escopo e aprovação

As automações e metadados nativos continuam configurações administrativas
globais do workspace. O adapter apresenta esse efeito explicitamente e exige
um administrador vinculado em `config/live-adapters-access.json`. Não infere
propriedade de registros legados nem muda roles/ACL existentes. MemPalace e
materiais continuam com seus vínculos próprios por empresa e usuário.

Os novos efeitos exigem aprovação humana mesmo com YOLO ligado. O servidor
vincula a aprovação aos parâmetros e ao estado do alvo/política, com validade
de 15 minutos. Alteração do alvo, expiração ou revogação bloqueiam a execução.
O modelo não recebe ferramenta para aprovar. Backups e propostas são
criptografados; os valores de credenciais ficam fora do chat e da auditoria.

O cartão mostra o alvo, escopo, hash e parâmetros completos da proposta.
Repetições e falhas incertas não repetem os efeitos automaticamente.

## Ativação de pesquisa e rollout

O plugin Pesquisa na Internet aparece no catálogo do repositório. Configure
Brave Search em Integrações, sem enviar a chave no chat. A chave e variáveis
`CUSTOM_` são retiradas do ambiente dos agentes CLI.

`config/live-self-healing.json` inicia com rollout desativado. Para ativá-lo,
o operador precisa instalar o workflow revisado `live-rollout.yml`, configurar
o ambiente GitHub `production` e cadastrar nos Secrets desse ambiente:

- `OMNINEXUS_VPS_HOST`
- `OMNINEXUS_VPS_USER`
- `OMNINEXUS_VPS_SSH_KEY`
- `OMNINEXUS_VPS_KNOWN_HOSTS`

O adapter verifica SHA, CI/build concluídos, workflow e executor idênticos aos
revisados, ambiente configurado, digest da imagem e versão anterior. A aprovação
humana no Live é sempre obrigatória, inclusive no uso individual por Felipe.
O operador pode habilitar `requireEnvironmentReview` para exigir também um
revisor no ambiente GitHub; o agente não pode enfraquecer essa política. O executor
na VPS verifica o label OCI, ausência de chamada/implementação ativa, faz
backup e muda somente a imagem do serviço fixo. Saúde não confirmada solicita
a imagem anterior já aprovada. Não expõe SSH/socket Docker ao agente Live.

Jobs retornam `jobId`; `pending`, `running` e `dispatched` não são conclusão.
Após interrupção em resultado incerto, reconciliar o GitHub antes de qualquer
nova tentativa. Ativar a política é uma ação do operador, fora das ferramentas
de escrita dos agentes.

## Verificação e teste no Live

Os testes usam arquivos/bancos temporários e rede/executores simulados:

```sh
.venv/bin/python -m pytest -q tests/backend/test_live_adapters.py tests/backend/test_live_self_healing.py tests/backend/test_live_github.py tests/backend/test_live_tool_audit.py tests/backend/test_live_handoff_controller.py
node qa/managed-live-context/handoff-tests.cjs
node qa/managed-live-context/tool-audit-tests.cjs
```

O teste do controlador percorre as 12 personas, incluindo entrada tardia de
transcrição e falha na gravação final, sem chamada real ao provider. O teste
do executor recusa revisão/digest divergentes antes de alterar um serviço.

Após a publicação, Felipe valida voz real em Hera → Dante → Vulcano → Sage →
Orion → Atlas → Íris, repetindo uma informação curta para conferir continuidade.
Com Lens, pedir PR 93 de `sistemabritto/omni-nexus-live` e todos os arquivos.
Com Atlas, pedir uma rotina de teste desativada de um executor registrado,
conferir o cartão e só então aprovar. Não usar remoção, agendamento ativo ou
rollout de produção como teste automático.

Referências de contrato externo:
[Brave Search](https://api-dashboard.search.brave.com/api-reference/web/search/get),
[GitHub Git trees](https://docs.github.com/en/rest/git/trees),
[GitHub workflows](https://docs.github.com/en/rest/actions/workflows) e
[ambientes protegidos](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
