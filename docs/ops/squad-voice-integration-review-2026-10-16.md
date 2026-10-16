# Squad antes da fila — lote dashboard sobre 2eed8fd

Integração de b0bfb19/4483d8b (voz por persona) e 2b192db (contrato de entrega), mantendo integralmente o worker e os motores de vídeo de 2eed8fd. PR92 não foi aplicado; nenhum retry, desbloqueio, reassignment, alteração de heartbeat, grant ou chamada remota foi executado.

## Comportamento revisável

- Preferência de voz distingue usuário, empresa, agente remoto e persona local. Preferência legada permanece baseline até escolha explícita local. NULL local restaura padrão somente naquela persona. A sessão usa a persona do contexto owned; o cliente não escolhe outra no signed-session. Nenhum voiceID real escolhido ou agente remoto alterado.
- Catálogo acrescenta trios/delivery_roles e display_label. Seletor Live apresenta função · apelido quando o catálogo fornece o rótulo; IDs/slugs/aliases e ACL preservados, fallback anterior disponível.
- POST /api/agents/delivery-contract/validate requer cookie pessoal, Origin HTTPS da mesma origem, empresa/personas autorizadas. Valida formato/versão de evidência, critérios e independência declarada; ferramentas não verificadas/dependências/métodos indisponíveis bloqueiam. Método vazio, UTF-8 inválido, acima256KiB ou resolvido fora do workspace não conta como disponível.
- candidate_complete NÃO é entrega aceita: evidência e ferramentas são declaradas e não verificadas; acknowledgement=not_recorded, ownershipChanged=false, dispatchAllowed=false e publicationApproved=false. O endpoint não consulta ou adota o ticket por taskId, não comprova autoria/hashes reais e não persiste aceite. A validação é pessoal e aditiva, não enforcement global do executor.

| Frente | Responsável | Apoio | Revisor |
|---|---|---|---|
| Operação | Clawdia | Atlas | Oath |
| Estratégia | Mako | Sage | Raven |
| Conteúdo | Pixel | Mako | Oath |
| Direção visual | Canvas | Bolt | Oath |
| Engenharia | Bolt | Hawk | Lens |
| Qualidade | Oath | Probe | Raven |

Compartilhamento é por entrega; revisor que participou da autoria não é independente. Nex/Dex e demais personas/tickets não foram removidos ou transferidos.

## Evidência e limites

76 testes locais de contrato/catálogo/voz/selector/handoff passaram;19 regressões adicionais de contexto/voz passaram (sobreposição, não somar como únicos). Provedores e vozes são fixtures; zero geração. 14 testes adicionais de auditoria/preflight passaram; TypeScript, ESLint e build Vite passaram (aviso de chunk grande já existente). O teste terminal HTTP local primeiro encontrou dependência express ausente no checkout; usando dependências já existentes, o listener foi recusado pelo sandbox listen EPERM127.0.0.1. Sem instalação nem contorno; CI deve executar a fixture HTTP antes de publicação.

Capacidade operacional real de ferramentas, aplicação das skills por um modelo, aceite do destinatário e QA independente de um entregável real permanecem não comprovados neste lote. Não liberar fila baseado só em metadados/trios. Escolhas de voz dependem de ouvir previews existentes e decidir explicitamente, sem geração paga neste lote.

## Aplicação proposta e rollback

Lote somente dashboard; worker deve permanecer no digest do vídeo 2eed8fd. Antes de qualquer aplicação: CI completo, imagem dashboard exata/boot smoke, ociosidade, backup consistente de SQLite/contextDB/config/sessões e snapshots de filas/ACL/preferências. Não iniciar conversa nem canário automaticamente. Rollback proposto restaura só dashboard para2eed8fd e mantém tabela aditiva de preferências sem uso, dados/ENV e worker. Não restaurar DB antigo por cima de dados novos.
