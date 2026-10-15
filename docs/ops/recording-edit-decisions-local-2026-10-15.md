# Gravações: cortes manuais e revisão versionada — lote local

Base: `050a8b5`. Branch: `feat/local-recording-edit-decisions`.

## Lacuna e alteração

O fluxo existente preservava brutos, montava prévias, recebia feedback e exigia QA humano antes de MediaRelease. Aplicar qualquer ajuste exigia editor externo/exportação. Este lote permite selecionar início/fim em segundos de cada vídeo, manter a ordem existente e gerar outra prévia pelo fechamento explícito do lote. Fotos/áudios continuam com os comportamentos existentes. Um trecho contínuo por vídeo; cortes internos, legendas e tratamento editorial avançado continuam externos.

As decisões pertencem ao snapshot imutável, com caminhos/hash resolvidos pelo servidor. A assinatura idempotente inclui cortes normalizados; repetição igual retorna a versão existente, alteração após fechamento retorna conflito. Requisições antigas sem cortes conservam a assinatura anterior. IDs não selecionados, parâmetros desconhecidos, booleanos, NaN/infinito e intervalos invertidos são recusados. O worker confere o intervalo contra ffprobe antes de executar o respectivo trecho, usa seek de entrada/reencode e preserva o mapa do tempo original. Não afirma que feedback livre tenha sido aplicado automaticamente.

A UI mostra os limites congelados por versão, recupera os cortes anteriores na nova edição e mantém seleção ao reabrir na mesma sessão. Recarregar a página durante um lote aberto ainda perde a seleção manual não salva, comportamento preexistente; conferir itens antes de fechar. Cada nova prévia continua exigindo QA do hash atual e aprovação MediaRelease própria.

## Evidência e limites

- PASS: `pytest tests/media/test_recording_edits.py tests/media/test_recordings.py -k "not closed_batch_worker_to_human_release"`: 27 passaram, 1 teste real de FFmpeg excluído; cenário completo mockado adicional passou. `pytest tests/media/test_recording_edits.py tests/media/test_media_release.py`: 44 passaram (avisos legados SQLAlchemy).
- PASS: após endurecer rejeição de inteiros gigantes, `pytest tests/media/test_recording_edits.py -k "invalid_trim or close_freezes"`: 12 passaram, 4 fora do filtro.
- PASS: `GRAPHIFY_MAX_WORKERS=1 nice -n 15 graphify update . --no-cluster`: 2.047 arquivos, 25.271 nós/41.624 arestas, AST local; aviso de parser SQL opcional ausente. Saídas geradas ficam fora do commit.
- PASS: TypeScript isolado do componente com dependências importadas e ESLint de `RecordingsQueue.tsx`; `git diff --check`.
- FAIL externo ao recorte: TypeScript global, `src/live/managed-session.ts:6,16`, TS2307, pacote `@elevenlabs/client` ausente no node_modules existente. Nenhuma instalação ou alteração nessa frente.
- PASS: contratos de API/worker com bytes sintéticos; isolamento, idempotência, snapshot v1 preservado e feedback vinculado à versão.
- PASS: comandos FFmpeg/ffprobe simulados conferem seek, duração, mapa original e preenchimento de silêncio; intervalo além do bruto falha sem subprocesso nesse trecho.
- PASS: cenário simulado com dois brutos → prévia v1 → feedback → cortes → v2 → bloqueio de QA da v1 → QA humano da v2 → aprovação → dois destinos Postiz simulados → confirmação simulada de agendamento/publicação. Isso não comprova entrega real.
- NÃO TESTADO no primeiro lote: render real, sincronismo perceptivo, navegador/mobile/teclado, contraste resolvido e distribuição real. O complemento abaixo cobre o render sintético. CPU carregada (~6 a ~10 para 4 CPUs), swap ~1,5 GiB; não iniciado render/build Vite pesado.
- Identidade visual: reutilizados os campos, cores e botões existentes; controles com labels/fieldset e grade responsiva. Revisão de código não certifica acessibilidade visual.
- Execução local efetiva pelo Codex desta sessão. Variante exata do modelo não exposta por env, arquivo da sessão ou metadados de thread disponíveis. Claude/OpenCode/Drael não foram acionados neste lote.
- Nenhum push, PR novo, deploy, alteração de credenciais ou chamada real a mídia/Postiz/harness neste lote.

## Checklist de teste real — executor integrador

1. Em janela de recursos autorizada, integrar/revisar o commit local e executar build/preview da interface. Verificar mobile, teclado, texto longo e mensagens de erro.
2. Com dois vídeos locais autorizados (um com áudio e outro sem), adicionar foto/áudio opcional; conferir upload não inicia edição. Escolher ordem, inclusão e trechos conhecidos.
3. Fechar explicitamente e executar worker compatível com `recording_batch:v1`. Comparar início/fim/áudio/quadro/duração da prévia com os originais; conferir mapa no resultado. Fim em branco deve usar o final do bruto.
4. Salvar feedback em texto/áudio; reabrir, alterar corte e fechar v2. Confirmar v1/feedback preservados e aprovação anterior indisponível para v2. Testar fim além da duração e recuperação por nova edição.
5. Conferir integralmente v2 e registrar QA do hash. Revisar destinos, copy, horário e privacidade no MediaRelease.
6. Parar antes de distribuir: obter autorização específica para conteúdo/destinos/horários reais. Só o integrador executa deploy/distribuição. Conferir evidência por canal e permalink nativo, sem inferir publicação de fila/inbox/privado.

Bloqueio remanescente após o primeiro lote: validação visual/render real e teste de entrega autorizado; o complemento abaixo fecha apenas o render sintético; automação de edição editorial/legendas não está implementada por este recorte. Gatilho histórico IG→TikTok/Shorts não foi recriado.


## Complemento autorizado: um render sintético curto

Em 2026-10-15, carga caiu para 2,71/4 CPUs; RAM disponível ~6,9 GiB. Verificação de processos não encontrou build/FFmpeg ativo; integrador avisado da janela. Executado com `nice -n 15`, sem serviço externo. Uma única prévia efetivamente renderizada pelo worker: 160×240, dois brutos sintéticos de 1 s gerados localmente, primeiro com tom de 440 Hz, segundo sem áudio. Cortes 0,6–0,9 s e 0,1–0,4 s.

PASS: duração final 0,621333 s (esperada 0,6 s, diferença 21,3 ms); mapa 0–0,3/0,3–0,6 s. Frame em 0,15 s verde RGB [0,255,0], em 0,45 s vermelho [254,0,0], confirmando trechos e ordem. RMS do trecho sonoro 2049,62; trecho silencioso 0,0. Validação ffprobe real, hash do MP4 e bytes servidos pelo endpoint conferidos. Não houve avaliação auditiva humana nem inspeção visual de UI; cores foram medidas por decodificação local.

O primeiro teste passou por essas verificações e parou numa asserção incorreta do próprio teste: o hash do snapshot está em `binding.render_sha256`. Corrigida a asserção, a retomada copiou exatamente o MP4 já gerado e reutilizou a duração dos segmentos, sem outro render. Validação de metadados, pixels e áudio repetida sobre os mesmos bytes. `pytest -q -s tests/media/test_recording_trim_smoke.py` com `RECORDING_SMOKE_REUSE_DIR` apontando à execução original: **1 passou**, 10 avisos legados SQLAlchemy.

PASS na retomada: QA com hash errado recusado, hash correto aceito, aprovação MediaRelease vinculada ao hash; duas solicitações de distribuição geraram somente 1 upload, 2 drafts e 2 agendamentos no fake Postiz. Reabrir bloqueou QA/distribuição antigos (409); fechar cortes alterados criou v2 sem QA e preservou snapshot da v1. Nenhuma chamada real ao Postiz.

Evidência estruturada versionada: [recording-trim-smoke-evidence-2026-10-15.json](recording-trim-smoke-evidence-2026-10-15.json). MP4 sintético local: `/home/sistemabritto/Documents/Codex/2026-10-15/task-3/recording-edit-decisions-evidence/synthetic-preview.mp4`. SHA-256 `33ee8a455b5e20e1faa4f59f4cd97ca088ea0f1fa66859f9461b5b080376e0ea`.

Checklist remanescente: integração pelo integrador; build com dependência Live restaurada pela frente responsável; browser/mobile/teclado/contraste; revisão humana de áudio, cortes e enquadramento em resolução real; teste de codecs/durações mais amplos; conteúdo/destinos/horários aprovados explicitamente antes de qualquer distribuição real. O teste sintético não autoriza conteúdo do usuário nem comprova entrega a redes.
