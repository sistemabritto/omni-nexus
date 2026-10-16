# PR90 pronta para revisão sobre produção7521b91 — sem rollout

Base exata `7521b9127f274fa20fa71dab0cb0e162d91ea4b7`. Checkout separado `video-project-release`, branch `review/video-projects-on-7521`. Contrato puro2280447 já é byte-equivalente ao existente e não foi duplicado. Aplicados sem conflitos os deltas5acfd41,7503c94,29e6952,d4b04a8,f78575d; integração inicialc081eca. Followup apenas fortalece o teste de COPY/import do worker e registra esta revisão.

## Escopo concreto

Cinco entradas combináveis em Gravações: long_cuts, enriched_edit, faceless, stickman e motion_vsl. O usuário fornece/revisa cenas e seleção editorial; isso não demonstra ASR/seleção semântica automática. Novas versões3 usam capability recording_project:v1; versões1/2 preservadas. Áudio source/provided ausente falha; somente silent admite mux de silêncio. Não há alteração de dependências/pins/ENV/credenciais, Live/voz/tools, providers/OmniRoute, PR91, scheduler/Telegram, campanhas ou thumbnails.

Nova tabela `recording_creative_reviews` via create_all, sem rewrite de colunas. Revisão vinculada a hash/versão/frames/duração/marca, sessão humana manage e revisor diferente do criador; revoga QA/MediaRelease quando alterada. Aprovação/canais/copy/settings/horário continuam separados. Nenhum projeto/job de produção criado ou reaberto por esta preparação.

## Evidência nesta integração

-117 testes passaram,344 avisos legados SQLAlchemy,76,69s: video_projects, media_creative_review, recordings, recording_edits, recording_editorial_review, recording_worker_packaging, media_release, media_stack_contract. Postiz e geração mockados; há fixture FFmpeg curta do teste legado, não render HF longo.
-Teste reforçado do COPY real do Dockerfile importa recording_render, video_project_spec e video_project_render em subprocesso isolado:1passou0,16s. Evita alegar import com arquivos fora da imagem.
-TypeScript completo tsconfig.app e ESLint dos três componentes:PASS, dependências existentes, sem instalação.
-Vite build completo:PASS7,03s; aviso de chunk>500kB, não erro novo.
-Smoke na imagem worker existente `excarplex/evo-nexus-media-worker@sha256:bff8ae530bf6a6d4d02e91f54aea9b5b2a60dee9a0ccddd0f213aeea65e887fc`, módulos novos RO em overlay técnico: Python3.11.2/HF0.7.64, import/HTML2s PASS; rede none, rootfs RO, tmpfs32MiB,1CPU/384MiB, sem mounts produtivos/credenciais, render/provider_calls0. É prova de compatibilidade com o runtime existente; NÃO é teste da imagem final nova.
-Probe600s/18.000frames160x90: somente preparação HTML/spec PASS. --render não executado.
-Diff de preservação sem mudanças em src/live, managed_live_context, live_voices, provider_fallback, heartbeat_runner/internal_ticket_draft, Dockerfile.dashboard/swarm, personas.
-Inspeção visual/browser completo NÃO TESTADA nesta integração. A restrição conhecida de Chrome/setsockopt permanece; não foi contornada. Evidência anterior do autor/CUA isolado não é aceitação produtiva.

## Serviços e próxima janela

Publicador `docker-publish-britto.yml` target=media gera SOMENTE dashboard (`Dockerfile.swarm.dashboard`) e media-worker (`Dockerfile.media-worker`) do SHA final revisado. Não publicar/runtime nem mudar scheduler/Telegram/OmniRoute. Não houve push, workflow, build/push Docker ou rollout deste lote nesta preparação.

1.Revalidar base: qualquer lote Live/voz novo exige rebase/revisão dos hunks comuns; este lote não incorpora b0bfb19 ou thumbnails.
2.CI integral do SHA final, publicação target=media e registrar ambos digests/OCI SHA. Smoke dashboard por digest com fixtures isoladas, schema novo e guidance presentes. Smoke worker final por digest com imports/HF0.7.64/ffprobe/capability e fixture curta isolada, sem rede/provedores. Não usar overlay como substituto desse teste final.
3.Esperar término natural do canário/heartbeat atual e confirmar ociosidade real (CLI/Live/lock/runs/jobs); não matar execução nem mudar flags para abrir janela. Backup consistente DB/config/ENV/sessões/SQLite privado OpenCode e specs/compose; espaço livre mínimo4GB depois de staging+backup. Reinícios somente após gate.
4.Worker novo primeiro (compatível com v1/v2), depois dashboard novo. Preservar todos campos de serviceSpec exceto imagem, mounts/ENV/limites; manter continuidade ligada e Live tasks desligadas. O backend novo exclui workers antigos de v3 por listagem e claim. Sem reprocessamento automático de jobs antigos.
5.Verificar saúde, ambas revisões/digests, tabela aditiva, mesmas permissões/sessões/flags/config e fila; UI permite projeto sem uploads, legendas estruturadas e prévia. Teste pessoal segue checklist e PARA antes de aprovação/distribuição. Sem conteúdo social, voz paga, Postiz real ou grants novos.

## Rollback e limites obrigatórios

Dashboard anterior7521b91 digest `sha256:e298147154bbc004582d87990f10cb77eed96d2240a94f9216b81707ea58ad86`; worker anterior9b00b6f digest bff8ae... acima. Não restaurar DB/ENV antigo nem apagar tabela nova. Com zero projetos3 pendentes/em execução, retorno coordenado das duas imagens é simples após ociosidade. Se existir job3, parar/retirar consumidores antes de voltar backend antigo e manter esses jobs retidos até versão compatível; backend antigo desconhece o filtro capability3. Não converter snapshot para enganar worker antigo nem reabrir/reprocessar legado. Essa retenção deve ser explícita e auditada; não executar automaticamente fora da autorização.

Condições ainda abertas: imagem final Docker e seu render curto; UI browser/mobile completa; escuta/QA independente; marca/direitos reais; performance de vídeo longo em720p/1080p e ASR/seleção semântica. Com apenas uma conta humana na última verificação, o criador não consegue passar revisão independente: isso não bloqueia criar/ver prévia, mas bloqueia avançar ao aceite final. Não criar outra conta/grant nem enfraquecer gate como parte do deploy.

Recursos: builds em GitHub Actions, não PC. Smoke1CPU/384MiB temporário. Captura futura apenas serial,1worker, com RAM/CPU suficientes e timeout; probe600s160x90 não prova uma VSL longa em resolução final. O código aceita até3600s, mas esse teto de contrato não é prova de capacidade operacional.
