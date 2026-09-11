# Gambito de Valor v4 · entrega de 10/09/2026 BRT

## Escopo e decisão

Revisados os três artefatos compartilhados por Felipe. Preservados o naming
Gambito de Valor/Vibe Seller, o ping-pong do Magneto, o nome Consultoria a
Laser e as mudanças dos commits 2f0834c e b16a505. Não alterados stacks,
Remox, páginas comerciais ou campanhas antigas nesta revisão.

O mecanismo passa a exigir três saídas: ficha do gargalo, prova de utilidade
e captura medida. Retiradas promessas de venda sem esforço, exclusividade
por nomeação e números de resultados sem fonte. Relatos pessoais continuam
dependentes de confirmação de Felipe antes da gravação.

## Entregas

- Linha editorial v4: share LEgRBI38nYY7djWLRZUBJl89Q0VGzqyYDn6AlamVSJA.
- 35 fichas completas: share 3RkaDsIS-Qh-IRX4GNREHOtfDXK-99gklySm-3hVx74.
- Auditoria com agregados corrigidos e 47 cards preservados:
  share 9taF1Qyws3r9OPzsDuq77UXiAXuDxlONfOxPWFr56j4.
- Cinco recompensas reais no caderno:
  share hT98uG_BRgB8OPS8FBK_w3j8ccEsZqYB8Trc6TH3s6M.
- Inventário: workspace/social/gambito-v4-inventory.json. Todos draft_review;
  campaign_id e media_id nulos. Nenhuma campanha criada/ativada ou Reel publicado.

Gerador: scripts/build_gambito_editorial_v4.py. Fonte textual dos 35:
assets/strategy/gambito_reels_v4.py. Fonte original da auditoria preservada
no backup do workspace; gerar com --audit-source apontando para essa cópia.

Os links de recompensa usam /api/shares/{token}/view#SECAO porque o wrapper
/share não transmite fragmentos ao iframe. CTA final do caderno passa pela
rota /click, sem JavaScript. UTMs não equivalem a atribuição de lead/venda;
fluxo OpenReply permanece NÃO VALIDADO até teste com conta autorizada.

## Evidência e limitações

Soma dos 47 cards: alcance 51.678, plays 76.505, likes 988, comentários 664,
salvos 925, compartilhamentos 700. Soma de alcance por post não deduplica
pessoas. Coleta incremental e watch-time retroativo têm janelas distintas.
O segundo maior alcance é 9.131 (meme/controvérsia); outra demo de CRM tem
6.009, atrás da demo de 12.119. Ranking anterior foi corrigido.

Mantidas quatro falhas de processamento e ausência de interpretação visual.
Outlier average_watch_time de 113,05s/retention 100% requer conferência da
fonte; não reescrito por inferência. Não há atribuição de vendas nesta base.

HTML local validado em 390 e 1280 px, sem overflow horizontal: 35 artigos
de roteiro, 47 artigos de auditoria. Endpoints públicos dos artefatos testados
a partir da VPS; ambiente local recebeu 403 do acesso externo,
portanto não alegar teste universal de navegador no domínio público.

## Runtime

Quatro arquivos de skills instalados no volume ativo com backup em
/var/backups/gambito-skills-20260911T000927. Versões anteriores dos HTMLs
preservadas por scripts/publish_gambito_v4.py em /workspace/config/audits/.

Monitor reels-producer reativado após teste real de envio ao próprio Magneto
(sent=true) e repetição sem duplicação (sent=false). Identificada consulta
legada à tabela inexistente approvals; corrigida para pending_approvals.
Teste novo também encontrou ausência de collected_at causando exceção;
agora resulta em dado indisponível, não zero nem crash.

Overlay de dashboard copia somente reels_producer.py sobre a imagem vigente
cc1493ae2171b032696c7c67724fe209be36e9a8dfa46d9654b60e9d771fce2d,
preservada na tag evo-nexus-dashboard:gambito-v4-base. Scheduler continua
com limite de 2 GiB. Não havia heartbeat running antes do rollout.

Pixel e goal-planner ainda tinham como último resultado as execuções
interrompidas pelo deploy anterior. Esta entrega não comprova recuperação
dessas chamadas de modelo; não esconder esses alertas nem marcar sucesso.

20 testes direcionados passaram, incluindo gerador, esquema real de
aprovações, evidência ausente, deduplicação do monitor e contrato Telegram.

Rollout concluído: dashboard 769d8260c7df healthy, imagem gambito-v4.
Teste posterior retornou dois alertas históricos (Pixel e goal-planner),
sem falso alerta de banco. Envio confirmado e segunda chamada sem duplicação.
