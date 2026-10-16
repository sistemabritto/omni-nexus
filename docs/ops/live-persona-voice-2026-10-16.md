# Voz por persona — correção local sobre7521b91

Causa: VoicePicker recebia só companyId; a preferência era chaveada por usuário/empresa/agente remoto. A persona local nunca participava da escolha. O signed-session também consultava a preferência sem o agent_name do contexto autorizado.

Mudança: parâmetro agentName no catálogo/save; validação pelo mesmo _scope de empresa/persona/ACL. Nova tabela aditiva persona_voice_preferences com chave usuário/empresa/agente remoto/persona. Tabela legada intacta: serve de baseline quando ainda não há escolha local. NULL local explícito significa padrão do provider somente nessa persona, sem apagar a escolha legada. Sem migração, clone automático de preferência ou alteração remota. Clientes antigos continuam no escopo legado.

A sessão usa row.agent_name do contexto owned, nunca um slug enviado no início da chamada. O catálogo visual remonta por empresa+persona para cancelar requests/preview antigos; salva e busca com a persona selecionada. Toda compatibilidade/permissão de voz e bloqueio quando override não permitido permanecem. Não configura vozes diferentes automaticamente; habilita escolhas independentes.

Testes: metadados/IDs totalmente sintéticos, requests provider mockados; isolamento entre personas/empresas/providers, preferência legada preservada, reset local durável, ACL antes de requests, sessão vinculada ao contexto e override negado. Nenhum áudio novo ou ID real usado. Os19testes simulados passaram na rodada conjunta; um teste HTTP real do terminal foi impedido pelo sandbox (listen127.0.0.1 EPERM), não falhou por contrato de voz.

Validação após integração pelo publicador único:
1. Confirmar diff sobre HEAD corrente, testes e backup normal do arquivo de contexto antes do rollout habitual; nenhuma publicação concorrente.
2. Abrir duas personas autorizadas na mesma empresa. Conferir preferências legadas preservadas e controles independentes após uma escolha explícita. Testar troca rápida e retorno sem catálogo/preview da persona anterior.
3. Ouvir somente previews existentes; verificar pausa no início da chamada. Ouvir preview não salva. Não usar síntese para testar.
4. Após escolha explícita autorizada, salvar preferência de uma persona, recarregar e comparar com outra, outra empresa e usuário autorizado. Restaurar padrão em uma não apaga a outra nem a preferência legada. Não escolher IDs reais nesta auditoria.
5. Só validar voz numa conversa nova com consumo já autorizado; não iniciar chamada paga para esta auditoria. Sem override permitido, escolha não inicia silenciosamente com outra voz.

Rollback: reverter código; tabela adicional pode permanecer sem uso. Preferências legadas e conversas existentes não foram migradas. Nenhuma voz/grant/provider remoto foi alterado nesta entrega.
