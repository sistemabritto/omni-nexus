# Correções locais do OmniNexus Live — 20/10/2026

Base: `release/live-experience-v2-reviewed`, `90a2771`. Branch isolada:
`fix/live-handoff-read-catalogs`. O checkout principal, em `main`, não contém
o Live atual. Nenhuma publicação, reinício, alteração de credencial, preferência
pessoal de voz, agente remoto ou índice produtivo foi executada.

1. **Transferência de voz: causa confirmada e correção.**

   Na leitura dos últimos 50 registros de conversa do provedor, Dante apresentou
   duas falhas, Vulcano uma e Sage duas, todas com código 1008 e recusa por
   moderação ao vivo da voz. Metadados atuais confirmaram
   `sharing.live_moderation_enabled=true` nas três vozes; Íris e os outros oito
   padrões do squad estavam com `false`. O app só verificava safety, autorização,
   verificação e fine-tuning, aceitando vozes incompatíveis com Agents.
   A restrição consta na [documentação oficial](https://elevenlabs.io/docs/eleven-agents/customization/voice)
   e o campo na [API de vozes](https://elevenlabs.io/docs/api-reference/voices/get).

   O resolvedor agora rejeita essa restrição tanto na listagem quanto no detalhe.
   O handoff prepara contexto/voz/URL do destino antes de encerrar o socket atual;
   falha nessa preparação preserva conexão e microfone anteriores. Retornos e logs
   distinguem voz indisponível, incompatível, moderada, override negado e assinatura
   da sessão, sem registrar URLs assinadas, tokens ou respostas brutas do provedor.

   Padrões locais substituídos: Dante → Thiago (Natural and conversational),
   Vulcano → Danilo Tenfen (Documentary Voice), Sage → Jeremias (calm & smooth).
   As três vozes já constam na conta, têm acesso confirmado, português verificado,
   fine-tuning para `eleven_v4_turbo` e moderação ao vivo desativada. Íris e os
   demais padrões permanecem. Preferências pessoais explícitas continuam tendo
   precedência e não foram regravadas. A qualidade auditiva será avaliada por Felipe.

2. **Skills, heartbeats e materiais: limites que pareciam falta de acesso.**

   O sanitizador reduzia listas a 40 itens e depois podia transformar JSON em
   texto cortado. Skills devolviam 25 resultados sem continuação; a leitura parava
   em 12 mil caracteres. Artefatos listavam somente 12 itens próprios do Live,
   sem materiais explicitamente vinculados ou roteiros de Gravações.

   Agora há índice compacto completo de skills e de heartbeats, inclusive legados.
   Skills/artefatos longos têm `nextOffset`; detalhes de heartbeat usam `identifier`.
   Materiais incluem somente arquivos previamente vinculados ao usuário/empresa
   e roteiros correntes com ACL e hash válidos. IDs `file:` e `recording:` são
   opacos; as leituras revalidam autorização e revisão. Vídeos continuam sendo
   uma amostra recente, declarada como tal. Nenhuma pasta global foi assumida
   como propriedade da empresa.

   Estado produtivo consultado: seis artefatos textuais dos handoffs de Felipe,
   zero arquivos externos vinculados e zero Gravações na Sistema Britto. O roteiro
   “Drael, episódio um” não foi localizado nessas fontes. Corrigir acesso não cria
   esse documento nem comprova onde ele foi originalmente salvo.

3. **MemPalace: ligação de leitura com atribuição registrada.**

   O índice tem 1.110 documentos e metadados de origem/autoria, mas nenhuma chave
   de empresa ou usuário. Wings/rooms não são ACL. A consulta Live só expunha o
   status; `/query` excluía o índice global. A memória dos agentes também contém
   referências a vários projetos, impedindo inferência automática de ownership.

   Felipe indicou nesta conversa que o legado atual pertence à Sistema Britto,
   com classificação futura por tenant. Essa atribuição provisória foi registrada
   em `config/live-mempalace-access.json`: IDs e SHA256 exatos do inventário atual,
   empresa 1 (`sistema-britto`), usuário 1, compartilhados por todos os agentes do
   squad desse mesmo escopo. Não altera autoria histórica nem reescreve o índice.

   O adapter seleciona os IDs autorizados antes de `collection.get`; nunca faz
   busca vetorial global para depois filtrar. Revalida manifest, empresa, usuário,
   permissões `memory:view` e `mempalace:view`, hash e conteúdo antes do retorno.
   Revogação, alteração de conteúdo e permissões removem o resultado. O índice é
   paginado e a busca é lexical, via `search_omni_context` e leitura da sessão já
   existentes; nenhuma chamada de embeddings/modelo, mineração ou nova tool é
   necessária para a consulta comum. O servidor não oferece autoatribuição ao agente.

   No conteúdo atual, 1.103 registros passam pelo filtro existente e sete ficam
   indisponíveis por esse filtro. O retorno distingue quantidade vinculada e
   disponível. Novos IDs e hashes alterados não herdam o vínculo. Outras empresas
   e usuários continuam sem essas memórias. A divisão empresarial futura exige
   revisão do manifest, não atribuição por nome de pasta ou de agente.

   Inventário privado de procedência, sem texto das memórias:
   `/home/sistemabritto/Documents/Codex/2026-10-20/live-handoff-review/mempalace-ownership-review.json`.

4. **Editor de Vídeo: responsabilidade definida no fluxo existente.**

   Dante responde pelo editorial; Íris pela direção visual; Vulcano pela execução
   com adapter verificado; Argos seleciona revisão independente; Felipe aceita a
   versão/hash. Entradas, beat sheet, entregas e critérios estão em
   `docs/agents/video-editor-role.md`, referenciado pelo perfil/persona do Dante.
   A skill `video-editorial-pipeline` já existia. O papel não cria heartbeat ou
   prova que o Live tenha adapter de edição fina. Sem esse adapter, entrega plano
   e direção; a fila de geração em rascunho não equivale a edição de bruto.

5. **Plugin GitHub configurável no painel.**

   Criado `plugins/github`, com manifesto, documentação e skill. Ele é descoberto
   pelo formulário existente de Integrações: **GitHub → Configurar**, campo de
   token protegido, salvar e testar conexão autenticada. A credencial é mantida
   pelo servidor e recarregada em processo; não é fornecida pelo pacote. O teste
   usa Authorization em header, sem seguir redirects; erros não devolvem o token.
   A credencial também é removida do ambiente dos subprocessos dos agentes.
   Cadastrar token invalida o teste anterior; presença de credencial não vira
   prova de saúde ou de acesso a todos os repositórios.

   A política local permite Felipe/Sistema Britto acessar todos os repositórios
   de `sistemabritto`, com leitura e escrita no adapter. Leitura: repositórios,
   PRs, arquivos de diff, issues, commits, branches e releases. Escrita: comentários,
   revisões e operações de dados suportadas pelo adapter. DELETE, administração,
   transferências e force push estão bloqueados. Revisões formais exigem Lens,
   SHA corrente e recusam autor/contribuinte da conta autenticada. A regra de
   independência da conversa permanece nas instruções; esse teste de identidade
   GitHub não substitui revisão da procedência de contribuições feitas por bots.
   Escrita usa o gate do app, auditoria e reserva durável contra replay incerto.

   A conta GitHub local consegue ler e escrever nos 23 repositórios encontrados;
   um PR existente foi lido sem mutação. Isso não é a credencial do plugin. Felipe
   deve cadastrá-la pelo painel após integrar esta versão. Nenhum token foi
   transferido automaticamente da máquina para o Live.

6. **Verificação e ativação pendente.**

   Os testes usam Flask/SQLite reais em arquivos temporários, manifestos reais e
   HTTP/socket/áudio sintéticos. Cobrem catálogo de 236 skills, 80 heartbeats,
   roteiros, tenant/usuário/hash/revogação, as 12 personas, falha antes de desligar
   o áudio, erros de socket, plugin descoberto/configurado/testado pelo mesmo
   endpoint do painel, bloqueio de DELETE e proteção de credencial. A suíte
   final passou com 122 testes; TypeScript `--noEmit`, ESLint dos módulos alterados
   e `git diff --check` também passaram. Há 20 avisos já existentes da consulta
   de tickets SQLAlchemy. Uma rodada anterior mais ampla passou com 163 testes.
   Um mock de AudioContext da regressão antiga foi corrigido: faltavam analyser
   e disconnect, e o mesmo teste falhava na base sem esta correção de produto.

   Sem testes de voz pagos, escuta humana, publicação, deploy ou reinício. O
   navegador real do painel/Live não foi testado nesta entrega; o teste do plugin
   percorre os endpoints reais usados pelo formulário. Graphify foi atualizado
   com AST, sem LLM; arquivos gerados ficam fora do commit funcional.

   Para ativar: integrar/deploy desta branch e os manifests de acesso no volume
   de configuração vigente; revisar os schemas de tools em
   `config/live-experience/client-tools.json` e o prompt correspondente. O script
   de configuração agora aponta schemas existentes divergentes e para antes de
   escrever; a migração deve preservar outros consumidores desses tool IDs.
   Nenhum desses passos remotos foi executado. Depois, cadastrar a credencial
   GitHub no painel e testar; confirmar transferências para os quatro agentes,
   consultar memória conhecida por mais de uma persona, paginar o índice e
   verificar ausência das memórias ao trocar empresa/usuário.
