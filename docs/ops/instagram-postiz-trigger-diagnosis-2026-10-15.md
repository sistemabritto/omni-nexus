# Instagram → Postiz → TikTok/YouTube: diagnóstico de15/10/2026

Consulta read-only concluída em17:46UTC. **O acionador original ainda não foi
localizado.** Isso não comprova que esteja inativo globalmente: pode existir em
outro executor/host/conta não identificado. Não criamos substituto ou reativação.

## O que foi localizado

- SQLite vivo do Nexus aberto com `mode=ro`: um trigger, id1, “Ghost publicou -
  distribuir nas redes”, enabled1, script ghost_published_to_social.py.
  trigger_executions tem zero linhas nessa base. A UI mostrar só blog corresponde
  a esse registro; ela não inventaria automaticamente executores externos.
- No Postiz instalado, transação PostgreSQL READ ONLY: AutoPost, Plugs, Webhooks,
  ExisingPlugData e IntegrationsWebhooks têm zero registros, inclusive na consulta
  sem filtro de deletedAt. Não apareceu configuração nativa de redistribuição ali.
- Código Postiz AutoPost encontrado é leitor de RSS; não é evidência de monitor
  Instagram configurado. O webhook Instagram do Nexus despacha comentários,
  mensagens e menções; não foi localizado handler de novo vídeo nesse fluxo.
- Fontes do repo, rotinas/config/scripts do container, cron e nomes de timers
  inspecionados não identificaram o watcher. O timer omni-reels-progress é um
  coletor de evidência read-only, não um distribuidor. Busca em mensagens de
  commits também não localizou implementação correspondente.
- Amostras dos containers atuais: scheduler18 linhas, dashboard1024, Postiz2047,
  limitadas a168h/últimas2500 linhas. Nenhum match dos marcadores de distribuição;
  ausência na amostra não prova ausência histórica, nem cobre containers antigos.
- Automations hospedadas acessíveis: duas entradas, nenhuma de Instagram/Postiz.
  Diretório de automações Codex local não existe no caminho consultado.

## Contas existentes — não criar nem trocar

| Papel | ID Postiz | Nome/provider observado |
|---|---|---|
| Instagram de origem | cmrry6y9g0001mi85746ikua2 | Felipe Britto · instagram-standalone |
| TikTok destino | cmrrzh5tk0001lm7yk41c3y6o | Workflow API Studio · tiktok |
| YouTube destino | cmrs1fplq0003pm86oxsfpb5u | Sistema Britto · youtube |

Essas três entradas têm disabled=false e deletedAt=null. Isso comprova cadastro,
não saúde atual de autorização/escopos nem propriedade por nome de exibição.
A entrada Instagram anterior, terminada em c2380cqr, está deletedAt desde julho;
não selecionar por plataforma sem excluir registros removidos.

Expiração de access token salva: IG16/11, TikTok24/09, YouTube30/09. Não
interpretar data vencida sozinha como desconexão: há renovação sob demanda no
Postiz. Não renovamos tokens, não testamos envio nem alteramos credenciais.
O rótulo TikTok difere do username histórico; confirmar identidade de origem e
destinos por IDs/provider antes de qualquer restauração, não só por display name.

## Redistribuição histórica comprovada, sem atribuir a um acionador

Postiz contém registros de vídeo creationMethod=API. A agregação excluindo
soft-deleted mostrou YouTube7PUBLISHED/7ERROR/3DRAFT e
TikTok1PUBLISHED/1ERROR/1DRAFT. Não há posts Instagram ativos nessa agregação.
PUBLISHED não significa necessariamente público: há canários YouTube privados.

| Rede | Postiz / evidência |
|---|---|
| YouTube CRM | cmuek212u0000ns8f71hi5t6l → native ID thhQQk9FHzk, typepublic, PUBLISHED |
| TikTok CRM | cmuekhupb0004ns8f19qsp3sc → UPLOAD, PUBLISHED, releaseId=missing, URL de messages/inbox |
| TikTok tentativa Direct Post | cmuekgx590003ns8fkhulj8sq → ERROR; último erro salvo unaudited_client_can_only_post_to_private_accounts |

O documento histórico de23/09 registra o proprietário concluindo TikTok no app,
com native ID7688834241236438279; isso não é nova verificação pública feita hoje.
O erro Direct Post é a última tentativa salva, não um teste atual da auditoria.
Não reexecutamos esses posts nem reabrimos campanhas/rascunhos encerrados.

Vários pares YouTube/TikTok compartilham a mesma referência JSON de mídia, mas
têm groups distintos, parentPostId=null e nenhuma URL Instagram de origem no
content inspecionado. O fingerprint dessa referência **não é SHA dos bytes do
vídeo** e não prova que diferentes renders sejam iguais. creationMethod=API
não identifica se foi agente, script ou acionador. A relação durável
source account/media ID → postiz ID por destino não foi encontrada.

## Correção isolada entregue junto a este diagnóstico

MediaRelease em preparação (PR80) aceitava todo PUBLISHED. A correção:

- YouTube privado/não listado e TikTok sem permalink nativo de vídeo permanecem
  awaiting_confirmation. Inbox/perfil/redirect/URL com credenciais ou host falso
  não viram publicação confirmada.
- Visibilidade remota reportada em settings deve coincidir com a aprovação.
- Preserva Postiz post_id e registra native_post_id separado quando há permalink.
  Reconciliar lê o mesmo post, sem upload/draft/schedule repetido.
- Remove URL/ID antigo quando o post deixa de aparecer; limpa aviso anterior
  quando chega evidência válida. Aprovação editorial/digest e gates permanecem.

Essa verificação confere formato de permalink e evidência Postiz; não faz uma
requisição anônima à rede para provar disponibilidade pública naquele instante.
Não cria listener, rotina, conta, serviço, replay ou publicação.63 testes passaram,
com os casos reais reproduzidos em doubles e regressão MediaRelease/Gravações.

## Recuperação mínima proposta — ainda sem ativação

1. Localizar executor/configuração/cursor originais (por exemplo, o identificador
   do fluxo lembrado ou endpoint onde foi configurado). Recuperar o existente,
   em vez de criar um segundo consumidor com os mesmos destinos.
2. Confirmar origem própria e os três IDs acima. Publicar no próprio Instagram
   não prova direitos de todo trecho; material com terceiros/direitos incertos
   continua em revisão. Vídeo inédito mantém aprovação editorial/versionada.
3. Dry-run de eventos novos com cursor inicial “agora”; nenhum replay histórico.
   Usar chave única por conta Instagram + media_id + integration_id destino;
   registrar separadamente hash do master/versão, Postiz ID, native ID e URL.
   Mudança de render exige nova decisão, não novo envio automático do mesmo evento.
4. Reconciliar IDs históricos conhecidos antes de qualquer criação. Timeout de
   criação vira resultado incerto e bloqueia retentativa cega, como MediaRelease.
   Dedup do MediaRelease é por job/release; não substitui dedup entre eventos/jobs.
5. Reusar Postiz e MediaRelease para destinos/copy/horário aprovados. TikTok UPLOAD
   exige conclusão pelo proprietário e permalink; YouTube exige visibilidade
   pública explícita para contar como publicação pública.
6. Somente o integrador restaura/implanta, após revisar o executor encontrado e
   uma peça/destino/horário especificamente autorizados. Nada foi ativado aqui.

## Limite de inspeção

A revisão automática de aprovação rejeitou uma consulta planejada a
Integration.profile por potencial exposição de segredos. O campo foi omitido
completamente na alternativa segura; a investigação usou IDs, nomes e estados,
sem ler/exibir token/refresh token. Não é necessário aprovar esse campo para
revisar este diagnóstico ou a correção de estados. Identidade atual completa do
provedor continua a conferir por um caminho de leitura seguro antes da ativação.
