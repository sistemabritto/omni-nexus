# Gravações: cortes internos e reprovação por versão

Base do integrador: `149c649d73599c436975069a36360709debf8012`, já contém cb915fb/9d27b75 e trims/QA anteriores. Branch `feat/recordings-editorial-review`, worktree separada `task-3/recordings-editorial-review`. Actions/publicação/VPS exclusivamente pelo integrador 01a13c9a-dd49-73a0-a0fc-87b82fb29016. Esta fatia não altera o lote anterior.

## Inventário verificado

| Etapa | Implementado e testado localmente | Limite |
| --- | --- | --- |
| Reel/roteiro, múltiplos brutos | Origem/referências, tenant, chunks retomáveis, hashes, duplicatas e ordem | Reel histórico exige classificação explícita por admin; gatilho IG não recriado |
| Confirmação de envio | Upload não enfileira; fechamento explícito recusa recebimentos incompletos e congela seleção | Feedback não dispara edição |
| Edição | Trim v1 preservado; novo conjunto de intervalos mantidos retira erros internos | 20 intervalos/vídeo, 200 segmentos/lote; sem efeitos/legendas novos |
| Prévia | Worker, mapa fonte→editado, MP4 e hash; smoke real abaixo | Mapa por segmento, não palavra a palavra |
| Feedback/reprovação | Texto/áudio por versão; nova rejeição humana imutável com motivo/autor/horário/hash | Sem transcrição automática, cancelamento de posts remotos ou reprocessamento automático |
| Aprovação | QA humano do hash e MediaRelease de versão/copy/canais/settings/horários | Reprovação/edição exige nova prévia e aprovação |
| Distribuição | Postiz com checkpoints/reconciliação e repetição sem duplicidade nos mocks | Nenhum envio real neste lote |

## Contratos e compatibilidade

`edits[upload_id]` aceita o trim anterior ou `{"keep_segments":[{"start_seconds":0,"end_seconds":1},{"start_seconds":2,"end_seconds":3}]}`. Os intervalos são mantidos e os espaços removidos. Exigem ordem cronológica sem sobreposição; fim nulo apenas no último intervalo. IDs/caminhos/hash continuam resolvidos pelo servidor. Campos desconhecidos, números inválidos, listas vazias/excessivas e sobreposição são recusados. Renderer usa FFmpeg/codecs/normalização/áudio existentes e emite um item no mapa por intervalo. Nenhum modelo/transcrição/provedor novo.

Snapshot v1 mantém o formato. Apenas segmentos múltiplos usam `edit_plan_version=2`. Worker continua anunciando `recording_batch=v1` e acrescenta `recording_edits=v2` em lista/claim. Backend novo exclui jobs v2 da listagem de serviço sem essa capacidade; claim v1 conhecido retorna 409 antes de mudar status. Worker novo assume ambos os formatos. Regressão replica o protocolo exato de lista/claim do worker149c649 e executa o módulo novo com ambos.

`POST /recordings/<id>/versions/<version>/reject` exige sessão humana manage/acesso à empresa, versão atual fechada, revisão CAS, motivo e hash real. Nova tabela `recording_rejections` via `db.create_all()` habitual, sem modificar colunas legadas. Decisão é imutável e retries iguais são idempotentes. Revoga QA/approval digest, cancela o job usando transição existente e preserva vídeo/snapshot/feedback. A versão não volta à fila nem pode ser aprovada; reabrir/fechar cria outra prévia. Atualização CAS do release ocupado impede rejeitar durante distribuição. Se já existe post/estado de envio, recusa com indicação de revisar no destino; não promete desfazer publicação remota.

## Evidência

- PASS: `pytest -q tests/media/test_recording_editorial_review.py tests/media/test_recording_edits.py`: 25 testes, sem render/rede.
- PASS: `pytest -q tests/media/test_recording_editorial_review.py tests/media/test_recordings.py tests/media/test_media_release.py -k 'not closed_batch_worker_to_human_release'`: 51 passaram, 1 smoke antigo fora do filtro; 284 avisos legados SQLAlchemy.
- PASS: após acrescentar token/terminalidade, `pytest -q tests/media/test_recording_editorial_review.py -k 'rejection or internal_intervals'`: 2 passaram. Cobre isolamento, serviço recusado, CAS/busy/hash, reprovação persistida, prévia preservada, nova versão e distribuição mock em duas chamadas com somente 1 upload/1 draft/1 agenda.
- PASS: TypeScript isolado do componente/dependências e ESLint; sem build Vite. Tokens/componentes existentes mantidos; labels/fieldset e controles nativos, sem novo design system.
- PASS: `GRAPHIFY_MAX_WORKERS=1 nice -n 15 graphify update . --no-cluster`: 2.089 arquivos, 25.663 nós/42.440 arestas, AST local; aviso de parser SQL opcional ausente. Saídas geradas fora do commit.
- PASS: um render sintético efetivo em janela com carga 3,32/4 CPUs e RAM disponível ~6,7 GiB, sem build local do integrador. Baixo paralelismo e `nice -n 15`, somente fontes geradas localmente.

Smoke: `RECORDING_SEGMENTS_SMOKE=1 RECORDING_SEGMENTS_EVIDENCE=<pasta> pytest -q -s tests/media/test_recording_kept_segments_smoke.py`: **1 passou em 1,97 s**. Dois brutos; A mantém 0,1–0,3 e 0,6–0,8 s; B sem áudio mantém 0,1–0,3 s. Prévia 160×240 com 0,621333 s vs 0,6 s (padding AAC ~21 ms); mapa 0–0,2/0,2–0,4/0,4–0,6 s. Pixels vermelho/verde/vermelho [254,0,0]/[0,255,1]/[254,0,0]; RMS 2023,87/2034,11/0. Folha de quadros inspecionada via view_image: sequência e enquadramento centralizado preservados, faixas pretas. JSON em `recording-editorial-review-evidence-2026-10-16.json`; MP4/frames fora do repo em `/home/sistemabritto/Documents/Codex/2026-10-15/task-3/recordings-editorial-review-evidence/`.

NÃO TESTADO: escuta humana, UI em navegador/mobile/zoom/leitor/contraste resolvido, rosto/texto real, distribuição real. Medição de áudio não equivale a QA auditiva humana. Nenhuma dependência/repositório instalado; nenhuma chamada Claude/OpenCode/Drael/modelo, mídia paga, credencial, postagem ou agenda real.

## Checklist do integrador e rollback

1. Revisar/aplicar commit sobre release atual, preservar packaging de recording_edits e criar tabela nova no startup habitual antes de servir rotas. Não remover tabelas no rollback.
2. CI/build e smoke da UI/API. Testar lista/claim de worker v1 e novo com ambos os formatos. Publicar app/worker coordenadamente; não reabrir/reenfileirar conteúdo como efeito do deploy.
3. Reverter a fatia inteira quando necessário. Trims v1 continuam operantes. No rollback para app antigo, manter jobs v2 parados até worker compatível; um worker antigo que os receba recusa trim desconhecido, não transforma intervalos em bruto completo. Não reescrever snapshots para forçar execução.
4. Reprovação deixa job cancelado, QA vazio e digest revogado também para app antigo; rollback não restaura aprovação. Não retentar esses jobs; criar nova versão explicitamente.
5. Exercitar campos/remoção/overlap, reabrir, histórico, motivo obrigatório e recusa de reprovação após envio remoto. Conferir keyboard/mobile e leitura dos estados de erro.
6. Revisar visual e auditivamente na resolução real antes de QA. Salvar alterações fechando lote: edição ainda não enviada é estado local e pode se perder ao recarregar página.
7. Aprovar hash/versão e cada canal/copy/horário novamente. Distribuição real só com autorização específica do conteúdo/destinos/calendário; reconciliar prova nativa por canal, sem inferir publicação de fila/inbox/privado.

Limites funcionais restantes: persistência da edição aberta antes do fechamento; montagem editorial avançada/legendas/transcrição automáticas; QA humana e validação real por canal. O circuito manual múltiplos brutos→edição→prévia→feedback/reprovação→nova versão→aprovação→distribuição está implementado e testado localmente; publicação do software fica com o integrador.
