# Contrato editorial de vídeo — handoff ao integrador

## Entrega

Skill original `.claude/skills/video-editorial-pipeline`, com referências
progressivas para faceless e brutos pessoais. Pixel passa a descobrir a skill;
o worker a inclui no catálogo da imagem, e social-media-production aponta para
ela quando pertinente. Papéis: Pixel editorial, Bolt implementação, Probe QA,
Felipe aprovação. Não alteramos reels-copilot, suas campanhas ou seus defaults.

Contrato executável `dashboard/backend/media_editorial.py` ligado à blueprint
existente: `POST /api/media/editorial/plan`, permissão execute, apenas cálculo e
resposta JSON. Não escreve banco/arquivos, não chama modelo/transcrição/Postiz e
não enfileira. Planeja os job types reais `social_clip` / `corte_bruto`, com
continuação nos estágios atuais; fixtures exercitam planejamento e criação
subsequente simulada de ambos os tipos no API real.

Mapa de tempos [start,end) e captions derivadas dos intervalos mantidos; corta
palavras inteiras, rejeita bordas dentro de palavras, tempos inválidos,
overlap/reordenação de keep e transições que dividem palavras. Glossário aplica
grafia de marcas sem alterar relógio. Revisões 2+ exigem referência à anterior.
Caminhos relativos e direitos declarados com evidência; não há leitura/coleção
de mídia, prova de licença ou resolução de symlinks neste planejador.

Seleção de transcrição é provided ou whisper_local explícito com modelo
multilíngue, sem executar ferramenta. Facebox é configuração normalizada, não
tracking. Frame sampling só especifica amostragem de até 80 frames. QA exige
áudio, captions, face, safe zones, direitos, overlap e transparência: são tarefas
de inspeção, não resultados medidos automaticamente pelo endpoint.

Fontes têm atribuição em references/sources.md. A síntese do PDF foi recebida do
coordenador; não alegamos ter lido/materializado seu original. Nenhum código,
mídia ou prompt extenso das fontes foi incorporado; SeeCut Noncommercial não
entrou na implementação. Nenhuma dependência foi adicionada.

## Gates e limites

Resposta sempre awaiting_beat_sheet_review, inclusive se o cliente enviar
approved=true ou approver=Felipe. O agente deve apresentar o beat sheet na
conversa existente; não há novo gate persistido, card Telegram ou notificação
implementada. Após decisão humana, ele cria explicitamente o job existente.
Rough cut primeiro; efeitos depois. Aprovação final e autorização de conteúdo,
destino e horário são distintas da aprovação do plano. O planejador não chama
approve/create-draft/schedule; não muda a máquina de estados do worker. O contrato final persistido de release
abaixo substitui a distribuição legada sem digest.

Brutos: color grading, memes e montagem fina são handoff para edição aprovada;
corte_bruto não ganhou esses efeitos. Cada corte adicional invalida o mapa da
revisão anterior. Os executores legados ainda não emitem mapas completos entre
etapas; não afirmar rastreabilidade automática de ponta a ponta. Antes de usar
o mapa para efeitos, gerar o mapa exato do estágio real ou reiniciar o plano
sobre a nova fonte/transcrição autorizada. Backups de revisões são obrigação do
executor/agente; o campo previous_revision não faz cópia de arquivo.

## Teste e integração

Comando local:

```
/home/sistemabritto/Documentos/evo-nexus/.venv/bin/python -m pytest tests/media/test_media_editorial.py tests/media/test_routes_media_jobs.py tests/media/test_media_workspace.py tests/media/test_state_machine.py -q
```

Resultado: **114 passed**, 70 avisos legados de Query.get; sem falhas.
Validator skill-creator quick_validate: skill válida. O novo teste entra no CI;
ao integrar PR32, que já amplia cobertura media, manter a união da seleção de
testes sem duplicação desnecessária. Dockerfile recebe apenas COPY da nova
skill, sem build/deploy nesta execução.

Checklist exclusivo do integrador 01a13c9a-dd49-73a0-a0fc-87b82fb29016:

- [ ] Revisar conflito no bloco de CI e Dockerfile.media-worker com PR32; no
  routes/media_jobs.py, este patch apenas importa módulo novo e adiciona endpoint.
- [ ] Integrar PR32/PR53 e os guardrails já revisados antes de testar worker real.
- [ ] Build de imagem preservando Live/UI/Portainer e seus parâmetros atuais.
- [ ] Smoke do novo endpoint com fixture não enfileira nada; flags de aprovação
  não retiram gates; material sem autorização/tempos inválidos recebem 400.
- [ ] Material real exige autorização específica; apresentar beat sheet, aprovar,
  executar rough cut, atualizar mapa/captions, prévia/snapshots e QA com timestamps.
- [ ] Aprovação final do Felipe via sessão humana de release antes de qualquer
  draft/agendamento; destino e horário autorizados explicitamente. Registrar confirmação no sistema de destino.

Nenhuma geração paga, instalação de repositórios, envio de áudio privado,
credencial alterada, publicação ou agendamento real. OpenCode/Claude Code não
invocados; Drael não selecionado e defaults globais não alterados. Sem deploy próprio.

## Evolução final — aprovação vinculada e distribuição por canal

Novo `MediaRelease` em models.py: tabela separada criada por db.create_all()
no startup habitual, sem reescrever colunas legadas. PUT/GET /jobs/<id>/release
criam/mostram snapshot canônico; /release/approve exige sessão humana manage e
digest atual, grava identidade real; Bearer de agente não aprova. SHA-256 real
do arquivo deve coincidir com o render validado do job. Versão, copy/canais,
settings e datas fazem parte do digest. Mudanças no job, arquivo ou revisão
invalidam; mudanças remotas na copy/conta/data também invalidam.

/release/distribute usa PostizClient existente com checkpoints persistidos por
canal: media id/path, post_id, state, remote_state, release_url e tentativas.
Verifica contas já conectadas; não conecta contas. Confirma QUEUE só com GET e
copy/conta/data exatas, PUBLISHED/URL só de evidência remota. /release/refresh
relê sem criar/agendar e funciona mesmo quando a aprovação foi invalidada.
Campo remoto conferido na documentação oficial:
https://docs.postiz.com/public-api/posts/list

Rejeição inequívoca tem no máximo 3 tentativas explícitas por canal. Timeout/5xx
ou resposta ambígua na criação bloqueiam em unknown; nunca recriar às cegas.
ID conhecido é reutilizado para status, canais confirmados não são recriados.
Lock busy persistido é adquirido atomicamente; queda exige reconciliação, sem
TTL automático. O fluxo não promete exactly-once diante de falha de rede: ele
para quando não consegue provar o resultado.

**Compatibilidade deliberadamente restrita:** /create-draft e /schedule antigos
retornam 409 bound_release_required. Não manter caminho sem digest. Atualizar
cliente/UI e a antiga simulação de happy path do PR53 ao integrar; o teste do
PR53 documenta o comportamento anterior. Novos testes de release substituem
seus cenários de upload/draft/retry e cobrem a distribuição multicanal. O endpoint
legado approve pode registrar revisão simples, mas não autoriza mais I/O de
publicação; PATCH do worker não promove status de aprovação/publicação.

**Painel integrado:** Media.tsx agora usa MediaReleasePanel para selecionar contas
já conectadas por nome, revisar copy/horário/versão e o snapshot, aprovar o digest
e acompanhar cada canal. Botões antigos de aprovação/publicação foram removidos
da tela; Live e outras áreas não mudaram. A API GET /media/channels apenas lista
contas suportadas ativas, sem expor configuração de credenciais.

**Bloqueios restantes:** teste real de ponta a ponta continua dependendo da
integração e autorização específica de conteúdo/contas/horários. Job cancelado ou aprovação
invalidada não cancela posts remotos já agendados; mostrar os IDs ao operador,
sem mudar Postiz sem autorização. Revisão não pode substituir release com post
criado/incerto até reconciliar. Atribuir a conta humana autorizada ao Felipe na
integração conforme as permissões existentes, sem inventar username/credenciais.

Checklist adicional: validar criação da nova tabela em cópia do banco; migrar
cliente e simulação PR53; exercitar stale digest/render alterado/copy/conta/data,
retry parcial, unknown e lock busy; somente então teste real de conteúdo e
canais/horários especificamente autorizados. Sem deploy nesta execução.

## Verificação da interface (somente simulação)

TypeScript: tsc -p tsconfig.app.json --noEmit com build info em /tmp.
Prévia temporária Vite com window.fetch totalmente substituído por fixtures,
sem backend/conta real. No navegador: selecionar conta, salvar revisão, observar
agendamento desabilitado, aprovar; editar copy bloqueia agendamento; salvar
revisão 2 remove aprovação herdada; aprovar novamente e distribuir produz estado
QUEUE e post_id fictício por canal. Após criação, edição de conteúdo/calendário
fica bloqueada até reconciliação. Captura local: task-3/release-panel-simulated.jpg.
A prévia e seus arquivos temporários foram encerrados/removidos; nenhum serviço
foi publicado.

Verificação final após a evolução de release/painel: **137 passed**, 286 avisos
legados de SQLAlchemy Query.get, sem falhas. Comando: pytest
tests/media/test_media_release.py tests/media/test_media_editorial.py
tests/media/test_routes_media_jobs.py tests/media/test_media_workspace.py
tests/media/test_state_machine.py -q. TypeScript final sem erros após remover
a fixture temporária da prévia. Skill quick_validate válida; diff --check limpo.

Regressão adicional: se o horário aprovado expirar durante upload/criação de
draft, o adapter invalida a aprovação e não chama change_status; não degrada
para publicação imediata. A suíte de release foi repetida após essa mudança.

A rodada final de release teve 28 passed; a regressão de calendário foi então
parametrizada para expiração antes do draft e durante sua criação, ambos
validados. A compilação TypeScript final e ESLint do novo painel passaram.
