# Isca, sessão e persistência — 10/09/2026

## Entregas

- Guia v4 no mesmo share público: `JmqUbtpIsv8eU8Gif-9XzmuU9w2O7S95M_g1pCxYMQ4`.
- Exemplos completos de robots.txt, sitemap.xml e llms.txt; auditoria por arquivo; configuração pontual da Cloudflare; duas capturas reais recuperadas do material de 04/09, identificadas como históricas.
- Não promete citação em IA. Busca, treinamento e acesso de agentes separados. Não recomenda desligar WAF. Referências externas verificadas: seis HTTP 200.
- Sessão com logo oficial, identidade escura/lima, proposta conectada ao funil, exemplo explicitamente ilustrativo, Felipe, escopo, condições e três CTAs. Mesmo checkout Cakto e R$ 150. Copy-framework/ui-conversion do lp-wizard e UI UX Pro Max aplicados sem escassez fictícia.
- Aula gratuita: nome e WhatsApp, sem OTP obrigatório; espera confirmação de gravação; erro inline preserva campos; acesso local por 30 dias. Isso não é autenticação nem verificação de propriedade do telefone.

## Causas confirmadas

1. `ShareView.tsx` carregava HTML por srcDoc com sandbox sem allow-popups: links target=_blank bloqueados. Além disso, srcDoc descartava a CSP do servidor e permitia scripts/same-origin. Agora iframe navega para /view com a CSP efetiva e sandbox opaco, sem scripts. HEAD identifica MIME sem somar visualização; GET conta a leitura.
2. `public.leads.email` é NOT NULL e UNIQUE (`leads_email_key`), confirmado por consulta de catálogo em produção. Cadastros por WhatsApp mandavam email vazio: todos após o primeiro conflitavam. Agora identificador interno determinístico por telefone, upsert ignoreDuplicates preservando o primeiro cadastro. Endereços `@sem-email.sistemabritto.com.br` NÃO são endereços de envio.
3. Serviço público do CRM procura contato por e-mail. OTP podia criar contato por telefone antes; o cadastro com e-mail sintético recebia conflito de telefone. Site tratava esse 422 como sucesso sem oportunidade. Agora reaproveita contato por telefone normalizado, confirma/cria oportunidade no pipeline de origem e não chama um 422 genérico de sucesso. Preserva estágio e atributos do contato existente.
4. Aula disparava gravação sem aguardar resultado. Corrigido: libera apenas após sucesso de ao menos um armazenamento, conforme contrato da API.
5. OTP compartilhado: erro de leitura/limites do banco agora falha fechado; 429 não informa success:true. Consumo exige atualização condicional confirmada, e código usado mais recente não permite fallback para código antigo. Não é uma reimplementação completa de limites atômicos distribuídos.

## Validação

- Backend Nexus: 25 testes de share/CSP/click/gate/URLs/mídia passaram.
- Site: 16 testes de checkout/atribuição/CRM/persistência/OTP passaram; build Next passou.
- Frontend Nexus: TypeScript + Vite build passaram.
- Navegador: 375/768/1440px, sem overflow; UTMs preservadas; guia light/dark.
- Fluxo aula com respostas controladas: falha não libera, mantém campos, reenvio bem-sucedido libera, reload mantém acesso; zero chamadas OTP.
- Produção: popup real para sitemaps.org a partir do iframe público abriu; sandbox sem scripts/same-origin confirmado.
- Produção: dois POSTs sintéticos com e-mail `.invalid`, sem telefone, origem `qa-funnel-20260910`, retornaram Supabase=true e EvoCRM=true. Supabase confirmou uma linha; consulta read-only no CRM confirmou um contato e uma oportunidade após os dois envios. Não houve envio intencional de mensagens ou compra. Excluir esse contato e visitas técnicas da análise de conversão.

## Deploy / rollback

- Site main: `5048286`, Vercel success.
- Dashboard Swarm: `evo-nexus-dashboard:share-links-20260910`, imagem `66bb9ffa989a9750a041a7e6ba016daa6d4fada6f6c4c01cc8e59d7a883f6c9e`. Receita `scripts/Dockerfile.share-links`, construída sobre harness-fix-20260909; Telegram e scheduler não alterados.
- Rollback dashboard: atualizar somente `evonexus_evonexus_dashboard` para `evo-nexus-dashboard:harness-fix-20260909` (reintroduz defeito dos links).
- Guia SHA256: `01660c5c6145bf3791d2b5d06db7c0072bfe4453f6873b305942985b939e1a62`.
- Backup da v3 preservado no volume workspace: `reports/backups/[C]guia-ia-before-tecnico-20260910.html`. Publicado atomicamente no caminho existente `reports/[C]guia-ser-mencionado-por-ia-v2.html`.
- Alterações preexistentes nos stacks e apresentações locais não foram incluídas nos commits.
- Em novo deploy pelo Portainer, preservar a imagem corrigida do dashboard ou usar uma imagem reconstruída deste commit. A stack local ainda referencia a tag remota latest e não foi redeployada integralmente.

## Limites / próximos acompanhamentos

- Correção não prova que a copy antiga causou a taxa de 1/65; havia um bloqueio técnico de links. Medir novo período.
- API mantém sucesso se ao menos um dos dois destinos gravar. Não há fila durável de reconciliação entre CRM e Supabase nesta entrega; monitorar falhas parciais. Não foi feito backfill automático de contatos antigos nem disparos.
- Deduplicação no Supabase preserva primeira origem, não registra cada recaptura. Eventos de cadastro no site distinguem o novo fluxo, mas ainda não são um histórico CRM de múltiplas atribuições.
- Demais áreas continuam com suas regras de acesso. Remoção de OTP limitada à aula gratuita.
