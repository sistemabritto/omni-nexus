# Gravações — MVP e handoff (15/10/2026)

Branch `feat/recordings-queue`, base `6d44af4` (PR56). PR empilhado: integrar
PR56 antes deste patch. Não implantar esta branch inteira sobre o Live atual;
o integrador deve reconciliar os pequenos hunks compartilhados em models.py,
app.py, media_jobs.py e Media.tsx. Nenhuma mudança de stack, sidebar ou Live.

## Comportamento entregue

Conteúdo ganha abas Gravações e Produções. A fila requer empresa selecionada.
Cada registro possui origem estável (Reel/roteiro/manual), roteiro e referências
versionados. A chave empresa+tipo+origem evita duplicar a mesma origem; reenvio
não sobrescreve o roteiro existente. Novas revisões preservam textos anteriores.
Reels legados não têm empresa confiável: apenas admin consulta fontes e as
classifica explicitamente. Não há backfill automático, execução do reels-copilot
ou exclusão de artefatos antigos. Referências duplicadas são preservadas.

Cada arquivo recebe ID próprio e fica em
`MEDIA_WORKSPACE/recordings/<empresa>/<gravação>/uploads/<id>/source.<ext>`.
Uploads de até 2 GiB (configurável por RECORDINGS_MAX_FILE_BYTES) usam chunks de
até 4 MiB, offset, hash por chunk e checksum final. A UI reserva todos os arquivos
selecionados antes de enviar bytes. Reeleger os mesmos arquivos permite retomar:
os chunks anteriores são reenviados para verificar igualdade e o servidor não
os grava novamente. Arquivos idênticos têm `duplicate_of`, sem apagar cópias.
Envio incompleto pode ser explicitamente excluído do lote, preservando os bytes.
Arquivos completos são preservados e selecionados/desmarcados para cada montagem.

Só **Tudo enviado — começar edição** cria um MediaJob `recording_batch`.
Todos os uploads pendentes precisam terminar ou ser explicitamente excluídos.
A operação usa revisão otimista e fecha o lote atomicamente com a nova versão/job;
repetir o mesmo fechamento devolve a versão existente. Antes de fechar, hashes
dos brutos são conferidos no disco. O worker confere novamente antes de renderizar.
O snapshot congela ordem, IDs, hashes e revisão de roteiro para essa prévia.
O claim devolve esse snapshot imutável, nunca o result_json de diagnóstico
mutável. Campos técnicos exigem serviço ou admin; render_path de um job de
Gravações fica limitado à própria pasta do job, inclusive para o serviço.

O worker monta localmente com FFmpeg: vídeos com áudio original (ou silêncio),
fotos com duração explícita e áudios avulsos sobre tela preta. Normaliza para
720×1280/30fps com letterbox, sem recortar o rosto. ffprobe valida o MP4 e SHA-256
vincula a prévia. Não chama modelos, OpenCode, Claude, transcrição ou API paga.
O mapa `rough_assembly_not_word_alignment` é de segmentos, não de palavras.

**Limite deliberado:** é uma montagem inicial, não um editor CapCut. Não gera
legendas, memes, correção de cor ou cortes semânticos e não interpreta feedback.
Para aplicar mudanças humanas: editar externamente, reabrir lote, enviar a
exportação e selecionar somente ela na próxima montagem. Os originais continuam
no registro. A UI explica essa operação. Não se deve confirmar QA de legendas
se a ausência delas não for intencional e aprovada.

Prévia, histórico e feedback texto/áudio pertencem a uma versão explícita. A UI usa
MediaRecorder quando disponível, com alternativa de anexar áudio. Áudio permanece
privado, sem transcrição automática. Chave idempotente evita repetir feedback em
uma retentativa; conteúdo conflitante na mesma chave recebe 409.

QA humano exige sessão de navegador, arquivo atual e cinco conferências (áudio,
legendas/ausência intencional, rosto, áreas seguras, direitos). A marca vale para
o SHA atual. Só depois aparece MediaRelease PR56: copy/conta/horário explícitos
por canal, aprovação humana do digest e distribuição/reconciliação por rede.
Reabrir o lote, rever roteiro ou criar outra prévia impede aprovação/distribuição
da anterior; arquivos históricos seguem legíveis. Mutação fica bloqueada enquanto
uma distribuição vinculada possui lock busy. O servidor revalida esses gates
antes de cada checkpoint de distribuição, além da verificação na UI.

Estados vêm de evidências: pronto para gravar → recebendo brutos → pronto para
editar → editando → revisão → aprovado. Agendado/publicado só derivam dos estados
confirmados de todos os canais do MediaRelease; entrega parcial e falhas têm
estados próprios. Um HTTP 200 ou um job antigo approved não viram publicação.

## Autorização e persistência

Sete tabelas novas via db.create_all; nenhuma coluna antiga é reescrita ou dado
histórico removido. CompanyContext é filtro local, não prova de autorização.
Admin possui escopo global; demais usuários precisam de permissão media_jobs e
grant explícito `RecordingAccess(user_id,company_id,level=viewer|editor)`.
Admin configura via PUT `/api/recordings/access` com esses campos. Sem grant,
a empresa/registro é 404; viewer não pode alterar. Não concedemos grants reais.

ACL cobre listagem, upload, originais, feedback, áudio e URLs diretas dos MediaJobs
vinculados (vídeo, logs e MediaRelease inclusive). A listagem genérica de jobs
filtra Gravações sem grant. Respostas privadas usam no-store. Jobs legados seguem
a política anterior: este patch não inventa propriedade histórica por empresa.
O usuário de serviço do worker precisa de escopo admin já existente ou grants e
permissões adequados; não alteramos credenciais ou papéis em produção.

## Validação local

109 testes na regressão combinada; 13 cenários de Gravações + 2 de render/storage.

- SQLite em memória: origem/revisões imutáveis; ACL entre empresas inclusive URLs
  diretas/lista de jobs; viewer/guest; offsets, reenvio de chunk e recuperação de
  chunk órfão; corrupção/checksum; fechamento idempotente/revisão obsoleta; ordem,
  duplicatas, exclusão lógica; feedback por versão/áudio; QA humano/hash e busy.
- Teste completo: upload → fechamento → claim `/run` → worker FFmpeg real → MP4
  privado → QA → MediaRelease → aprovação → dois canais Postiz simulados,
  retentativa idempotente → agendado e publicado confirmados pelo double.
- Smoke FFmpeg real: foto azul → vídeo vermelho com áudio → áudio avulso;
  dimensões/fps/duração/presença de áudio e pixels amostrados conferem ordem.
- Regressão de planejamento editorial, MediaRelease e rotas existentes.
- TypeScript, lint do componente novo e build Vite. Media.tsx conserva erros de
  lint anteriores (any e setState em effect); o novo componente passa isolado.
- Navegador com dados simulados, 375×812 e 812×375: fechamento bloqueado com
  parcial, exclusão lógica libera botão, fechamento abre revisão, feedback salvo
  na v1 e sem overflow horizontal. Reprodução nativa do vídeo não foi provada
  nesse mock; FFmpeg/endpoint de vídeo foram verificados pelo teste completo.
- Sem chamadas de produção, geração paga, postagem, agendamento real ou deploy.

## Checklist real — somente integrador

- [ ] Reconciliar PR56 e esta branch com a base atual, preservando PR65/Live/UI.
- [ ] Backup do SQLite e volume de mídia; confirmar tabelas novas sem alterar
      linhas antigas, mesmo volume/media path RW e FFmpeg no worker.
- [ ] Construir dashboard e media-worker juntos: Dockerfile copia os dois módulos
      novos de storage/render. Worker antigo não reconhece recording_batch.
- [ ] Testar empresa A/B com contas viewer/editor e grants explícitos; tentar
      também URLs diretas de vídeo/original/feedback/MediaRelease.
- [ ] No celular, salvar roteiro; enviar 2+ arquivos; interromper conexão, reselecionar
      e retomar; conferir ordem e duplicata; nenhum job antes do fechamento.
- [ ] Fechar um lote de conteúdo expressamente autorizado e verificar uma prévia;
      ouvir áudio, conferir duração, enquadramento, rotação, codecs de iPhone/Android,
      orientação do vídeo, fotos e qualquer área segura/legenda necessária.
- [ ] Enviar feedback texto/áudio na v1; aplicar edição humana e reenviar exportação;
      conferir v2 e histórico, impedindo liberação da versão anterior.
- [ ] Registrar QA humano só após inspeção real. Revisar copy, destino e horário
      específicos antes da aprovação/distribuição via MediaRelease.
- [ ] Somente com autorização específica, testar um canal; confirmar Postiz e
      estado remoto por canal; retentativas não podem criar duplicata.

Bloqueios restantes: integração/deploy exclusivo do integrador; teste físico em
celular e codecs reais; autorização do conteúdo/destino/horário para distribuição.
O MVP não implementa edição semântica automática nem transcrição paga.
