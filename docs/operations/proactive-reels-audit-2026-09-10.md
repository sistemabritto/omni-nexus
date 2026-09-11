# Auditoria operacional e coprodução Reels · 10/09/2026

## Evidências e mudanças

- Scheduler: kernel confirmou OOM do processo OpenCode em 09/09 às
  21:00:27, 21:01:29 e 21:02:45 BRT dentro do container com limite 1 GiB.
  Limite atualizado para 2 GiB, mantendo 1 CPU. Não é prova de que qualquer
  carga futura caberá; monitorar RSS e OOM durante rotinas reais.
- `ADWs.runner.summary` mostrava falhas, mas devolvia processo com exit 0.
  Agora encerra com exit 1 quando qualquer etapa falha. Isso impede o ✓ falso
  do scheduler e aciona a notificação de falha já existente.
- `pixel-growth-6h`: última falha observada antes da intervenção foi timeout
  de tentativa de 119 s dentro de orçamento total 300 s. Duas execuções
  anteriores do mesmo dia passaram (31,7 s e 175,2 s). Não é falha universal
  do provider. Atualizado para 600 s / 8 passos e escopo exclusivo goal 18.
- AI News Daily: timeout externo de 15 min, fallback Britto-Core/Britto-Coding
  com falhas. Desativada junto da pesquisa semanal correspondente, redundante
  com a esteira existente. Scripts e histórico mantidos, sem apagar dados.
- `Growth Pulse`: corrigidos meia-noite BRT→UTC, timeouts omitidos das falhas,
  janela de zumbis, falso custo zero, credencial presente ≠ integração saudável
  e sucesso de envio sem conferir retorno Telegram.
- Backup Watchdog executado: backup local e S3 recentes, idade 18,8 h.
  Não foi executado teste de restauração; saúde do backup não prova restauração.
- Heartbeats de integração/orquestração/publicação tinham últimas execuções
  success. Isso comprova execução do handler, não cobertura completa de todos
  os serviços. Autopilots antigos desativados foram preservados como histórico.

## Nova capacidade

- Goal 18: 11/09–10/10/2026 BRT, 120 Reels mínimos, 150 estendidos.
- Coleta `omni-reels-progress.timer`: leitura oficial Instagram a cada 30 min,
  campos id/media_product_type/timestamp/permalink, sem captions ou dados de
  leads. Ciclo finito; últimas leituras em 11/10. Paginação incompleta, fonte
  falha e evidência com mais de 2 h resultam em INDISPONÍVEL, não zero.
- `reels-producer`: handler Python, zero chamada de modelo, brief nas primeiras
  janelas após 07h/20h BRT; alerta por mudança de falha, sem mensagens 23h–07h.
  Deduplicação persistida no volume; falha Telegram não é marcada como enviada.
- Contagem distinta por ID com media_product_type REELS. Não conta tickets.
  Ainda não há deduplicação semântica de republicações com IDs distintos.
- Pixel: no máximo 2 pacotes completos por tick de 6 h, reserva-alvo 8
  roteiros aprovados, idempotência solicitada por data/slot via consulta prévia.
  Isso é controle por prompt, não garantia transacional de ticket único.
- Magneto recebe contrato completo ao detectar tema de Reel/gancho/roteiro/
  headline/estrutura de linguagem/OpenReply. Contrato instalado no volume compartilhado de skills.
- Recompensa antes de oferta; Sessão de Start R$150, sem herdar desafio
  ou R$147 da matriz antiga. Preserva pilares e identidade Vibe Seller.

## Testes e deploy

Imagem runtime `evo-nexus-runtime:proactive-reels-20260910`; dashboard baseado
em `evo-nexus-dashboard:share-links-20260910` para preservar a correção de links.
Backup das configs via `config/audits/proactive-*`; scripts/skill anteriores
em `/var/backups/omni-proactive-20260910` na VPS. Nenhuma campanha ou publicação
foi ativada durante a auditoria; nenhum lead recebeu mensagem.

Coleta inicial real: sucesso e paginação completa; zero no ciclo ainda não
iniciado. Teste real do handler: sent=true; segunda chamada sent=false.
Scheduler reiniciado com 20 rotinas, antes 22. Skill validada pelo validador.

### Interferência externa durante verificação

Às 15:57:09 BRT, evento Docker trocou apenas o dashboard de
`evo-nexus-dashboard:proactive-reels-20260910` para
`excarplex/evo-nexus-dashboard:latest`. Container saiu 143, OOMKilled=false.
Não foi a alteração feita por esta auditoria, nem rollback automático por
OOM. Testes ao vivo de goal-planner/Pixel foram interrompidos. Origem ainda
não identificada; usuário consultado para evitar disputa de deploy.
Não afirmar correção ponta a ponta desses agentes até nova execução concluir.
Dashboard latest voltou saudável, mas sem o módulo reels_producer. O heartbeat
novo foi pausado preventivamente, preservando coleta e relatório já entregues.
Runtime do scheduler e Telegram continuam na imagem nova. 27 testes passaram,
incluindo injeção do contrato no prompt. Os dois runs interrompidos foram
finalizados via step8_persist como fail/interrupted, preservando o histórico.
Relatório compartilhado e comunicado ao Telegram:
https://nexus.workflowapi.com.br/share/cdi3n-S6LlRg5I39x7v-H142pCMe-qD9UGA-1z4XF6s

## Próximas rotinas recomendadas

1. Pré-publicação: confirmar reward/link, keyword sem colisão, draft OpenReply,
   conta QA, webhook/worker; se media_id só existir após publicar, vincular e
   ativar imediatamente depois. Gate deve avisar Felipe, não apenas bloquear.
2. Revisão semanal: comparar retenção, salvamentos/alcance, DMs entregues,
   cliques, cadastros, sessões e pagamentos em coortes compatíveis. Falta de
   fonte deve gerar ticket de coleta, nunca conclusão de zero vendas.
3. Recuperação comercial: revisão humana dos leads antigos, identidade e
   consentimento; não colocar os recuperados automaticamente numa sequência.
4. Metas antigas vencidas: revisar/arquivar explicitamente; não retomar sprints
   de preço/WhatsApp de julho só porque ainda estão status active.
5. Restauração de backup em ambiente isolado mensal, com aprovação de recursos.

Referências técnicas: https://opencode.ai/docs/config/ (configuração inline e
snapshots); API Meta validada por leitura real de media_product_type=REELS.
