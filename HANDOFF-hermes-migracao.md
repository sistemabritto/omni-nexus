# HANDOFF — Migração Hermes: 4 serviços → 1 serviço com profiles nativos
Atualizado: 2026-07-16 ~23:10 (America/Bahia). Retomar daqui ao dar resume.

## Objetivo (pedido do usuário, ativo)
Migrar autonomamente os 4 Hermes antigos (mistica/excarplex/stoic/iron) para UMA stack
única com profiles nativos, dashboard em hermes.workflowapi.com.br, migrando TODO o
conteúdo, sem quebrar o que funciona, e avisar quando estiver no ar pra ele testar.
Stack final deve ser colada no Portainer.

## Acesso SSH (chave copiada para local persistente)
    ssh -i ~/.ssh/codex-hermes-swissnode-20260717 -o IdentitiesOnly=yes root@108.181.188.232
(cópia original em /tmp pode ter sumido após reboot do PC local — usar a de ~/.ssh)
Ao FINAL de tudo remover da VPS: sed -i '/codex-hermes-temporary-2026-07-17/d' /root/.ssh/authorized_keys

## Progresso (plano de 6 passos)
1. ✅ Auditoria completa (ver seção Fatos)
2. ✅ Backup de configs críticos: /mnt/docker-volumes/hermes-backup-20260717/critical-configs.tgz
   (dados brutos antigos permanecem intactos em hermes-profiles/ e hermes-shared/ = backup natural;
   NÃO deletar nada dos antigos até validação final)
3. ✅ Cópia bulk CONCLUÍDA (BULK_DONE 23:06): /root/hermes-migrate-bulk.sh gerou
   /mnt/docker-volumes/hermes-unified/ (~23G):
   - mistica → raiz do home (/opt/data = default profile)
   - excarplex, stoic, iron → profiles/<nome>/
   - hermes-shared/kanban → kanban/ na raiz
   - Excluídos: kanban/ individuais, .hermes-venv/, gateway.pid, processes.json
   - chown -R 10000:10000 aplicado
4. ⏭️ PRÓXIMO: escrever .env por profile + ajustes pós-cópia (ver TODO abaixo)
5. ⏭️ Stack nova + cutover (parar antigos ANTES — token lock do Telegram)
6. ⏭️ Validar 4 bots + dashboard + API mistica e avisar usuário

## TODO detalhado do passo 4 (pós-cópia, antes de subir)
No /mnt/docker-volumes/hermes-unified:
- [ ] Limpar lixo copiado da raiz (mistica trouxe): profiles/ vazio antigo já ok (agora contém os 3),
      verificar que profiles/ NÃO tem dir "iron" aninhado vindo de mistica/.hermes/profiles/iron
      (o rsync da mistica levou .hermes/ junto → checar /mnt/docker-volumes/hermes-unified/.hermes/profiles/iron
      e REMOVER esse .hermes/profiles pra não confundir; é lixo de 48K)
- [ ] Cada profile precisa de TELEGRAM_BOT_TOKEN no SEU .env (hoje tokens vinham das env da stack antiga):
      raiz (.env, mistica):  TELEGRAM_BOT_TOKEN=8741582155:AAFMFa-DAiGuzNeAFsqjtSnGx42Bu4Up1tM
      profiles/excarplex/.env: TELEGRAM_BOT_TOKEN=8776339773:AAFCEmZH-6wxrw0YwV03JXA0iHO9xWdrG3M
      profiles/stoic/.env:     TELEGRAM_BOT_TOKEN=8681412212:AAHTyA-MtGdWcZThtJ62YMf08cjDq0anQgo
      profiles/iron/.env:      TELEGRAM_BOT_TOKEN=8559821250:AAGVI2EMrP0Z0sx-cVlcFnbj4is1LPU4yeU
      (.env existentes já têm NVIDIA/OPENROUTER/OPENAI/GROQ keys, TELEGRAM_ALLOWED_USERS etc — só ADICIONAR o token)
- [ ] API server: só a mistica (default) mantém API_SERVER_ENABLED=true + API_SERVER_PORT=8642 +
      API_SERVER_KEY=hermes@Workflow01 → adicionar ao .env da RAIZ.
      Nos .env dos outros 3 profiles: API_SERVER_ENABLED=false (ou omitir) para evitar conflito de porta 8642
      (todos os profiles tentam bindar 8642 por default — fato verificado no código).
- [ ] Kanban: dispatcher deve rodar SÓ num gateway. Config kanban.dispatch_in_gateway=true está em TODOS
      os config.yaml → deixar true só na raiz (mistica); nos profiles setar false via
      config.yaml (kanban: dispatch_in_gateway: false) OU env por profile. Kanban root é compartilhado
      por design (<root>/kanban.db + kanban/boards/); board atual: felipe-pessoal.
      OBS: kanban.db da raiz veio da mistica; o shared tinha kanban/kanban.db (100K) — o bulk copiou
      hermes-shared/kanban/ → <root>/kanban/ MAS o default DB nativo é <root>/kanban.db (raiz!).
      DECIDIR: mover /mnt/docker-volumes/hermes-unified/kanban/kanban.db → <root>/kanban.db
      (sobrescrevendo o da mistica? comparar tamanhos/mtime primeiro). Boards ficam em <root>/kanban/boards ✔.
- [ ] gateway_state.json: raiz veio da mistica com desired_state=running (bom — autostart).
      Verificar profiles/*/gateway_state.json também estão "running" para o reconciler subir todos no boot.
- [ ] Modelos por profile (config.yaml já migrado carrega): mistica z-ai/glm-5.2, excarplex/stoic
      stepfun-ai/step-3.7-flash, iron minimaxai/minimax-m3 — nada a fazer (MODEL_DEFAULT env não é nativo, ignorar).
- [ ] SOUL.md existe em cada profile dir (marcador que o reconciler usa) — conferir nos 3 profiles.

## Passo 5 — Stack nova (dashboard auth OBRIGATÓRIO em bind público)
Credenciais geradas (usar estas):
  HERMES_DASHBOARD_BASIC_AUTH_USERNAME=felipe
  HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=kuj9HlNqzV7ZBFV0TRXZ
  HERMES_DASHBOARD_BASIC_AUTH_SECRET=3974a81dbcfaa416d15b19e6441ddfeb7927760c054b3a41ff7adddc71e3ae29
YAML alvo (stack "hermes2" via docker stack deploy; depois colar no Portainer):

```yaml
services:
  hermes:
    image: nousresearch/hermes-agent:latest
    command: gateway run
    stop_grace_period: 90s
    volumes:
      - /mnt/docker-volumes/hermes-unified:/opt/data
    networks: [network_public, hermes_internal]
    environment:
      - HERMES_DASHBOARD=1
      - HERMES_DASHBOARD_HOST=0.0.0.0
      - HERMES_DASHBOARD_PORT=9119
      - HERMES_DASHBOARD_BASIC_AUTH_USERNAME=felipe
      - HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=kuj9HlNqzV7ZBFV0TRXZ
      - HERMES_DASHBOARD_BASIC_AUTH_SECRET=3974a81dbcfaa416d15b19e6441ddfeb7927760c054b3a41ff7adddc71e3ae29
    deploy:
      placement: {constraints: [node.role == manager]}
      restart_policy: {condition: on-failure, delay: 15s}
      resources:
        limits: {memory: 8G, cpus: '4.0'}
        reservations: {memory: 1G, cpus: '0.5'}
      labels:
        - traefik.enable=true
        - traefik.docker.network=network_public
        - traefik.http.routers.hermes-dashboard.rule=Host(`hermes.workflowapi.com.br`)
        - traefik.http.routers.hermes-dashboard.entrypoints=websecure
        - traefik.http.routers.hermes-dashboard.tls=true
        - traefik.http.routers.hermes-dashboard.tls.certresolver=letsencryptresolver
        - traefik.http.routers.hermes-dashboard.service=hermes-dashboard-svc
        - traefik.http.services.hermes-dashboard-svc.loadbalancer.server.port=9119
        - traefik.http.routers.hermes-mistica.rule=Host(`mistica.workflowapi.com.br`)
        - traefik.http.routers.hermes-mistica.entrypoints=websecure
        - traefik.http.routers.hermes-mistica.tls=true
        - traefik.http.routers.hermes-mistica.tls.certresolver=letsencryptresolver
        - traefik.http.routers.hermes-mistica.service=hermes-mistica-svc
        - traefik.http.services.hermes-mistica-svc.loadbalancer.server.port=8642
networks:
  network_public: {external: true}
  hermes_internal: {external: true}
```

Sequência de cutover:
1. docker service scale hermes_hermes-mistica=0 hermes_hermes-excarplex=0 hermes_hermes-stoic=0 hermes_hermes-iron=0
   (OBRIGATÓRIO antes de subir a nova: token lock Telegram + conflito de router Traefik hermes.workflowapi.com.br)
2. docker stack deploy -c hermes2.yml hermes2
3. Reconciler de boot sobe gateways cujo gateway_state.json = running (default + 3 profiles).
   Se algum não subir: docker exec <cid> hermes -p <nome> gateway start / status / doctor
4. Logs: docker logs; per-profile em /opt/data/logs/gateways/<nome>/current

## Passo 6 — Validação
- Telegram: mandar msg nos 4 bots
- Dashboard: https://hermes.workflowapi.com.br (login felipe / senha acima; switcher de profiles)
- API: curl https://mistica.workflowapi.com.br/v1/models -H "Authorization: Bearer hermes@Workflow01"
- AVISAR O USUÁRIO para testar (requisito explícito)
- Manter serviços antigos em scale 0 (NÃO deletar stack antiga) por alguns dias
- Colar YAML no Portainer como stack (usuário quer Portainer como fonte)

## Fatos verificados (não re-auditar)
- VPS swissnode: Ubuntu 24.04, Swarm single-node manager, 8 CPU, 17.5G RAM, sem swap
  (sugerir swap 4G depois), 87G livres em /.
- Traefik v3.5.3, rede network_public, certresolver letsencryptresolver; rede hermes_internal existe.
- Imagem nousresearch/hermes-agent: HOME/HERMES_HOME=/opt/data, user hermes uid 10000,
  s6-overlay; `gateway run` CMD = heartbeat; profiles nativos em /opt/data/profiles/<nome>;
  reconciler /etc/cont-init.d/02-reconcile-profiles registra gateway-default + gateway-<profile>
  e auto-inicia os com estado running (draining/degraded contam como running).
  hermes -p <nome> gateway start|stop|status dentro do container via docker exec.
- Dashboard: 1 por container, porta 9119, serve todos os profiles via switcher; bind não-loopback
  EXIGE basic auth (HERMES_DASHBOARD_INSECURE é no-op). Plugin scrypt, env > config.yaml.
- API server: cada gateway tenta bindar API_SERVER_PORT (default 8642) se API_SERVER_ENABLED=true.
- Kanban: compartilhado por design no <root> (kanban_home() = raiz do home, não do profile);
  dispatcher tem lock global, mas melhor manter dispatch só na mistica via config.
- .env antigos NÃO têm TELEGRAM_BOT_TOKEN (vinham da stack); têm as demais keys.
- Perfis antigos magneto (4.8G) e excel (vazio) NÃO migrados (confirmar com usuário se quer).
- Clone do repo hermes-agent estava em /tmp/hermes-agent.eQE3XD (pode ter sumido com reboot;
  re-clonar de github.com/NousResearch/hermes-agent se precisar).

## Outras pendências da sessão (fora da migração)
- Postiz: RESOLVIDO (healthcheck temporal corrigido; arquivos locais postiz-vps.stack.yml:278 e
  docs/postiz-portainer-swarm.md atualizados, untracked no repo).
- Segurança: usuário expôs no chat tokens Telegram, NVIDIA key, OpenRouter key, API_SERVER_KEY —
  recomendar rotação após migração estabilizar.
- Recomendar criar swap de 4G na VPS.
