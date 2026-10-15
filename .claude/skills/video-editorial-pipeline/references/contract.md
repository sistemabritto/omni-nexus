# Contrato v1 — planejamento offline

Entrada de `POST /api/media/editorial/plan` (sem efeito no banco/worker):

```json
{
  "mode": "personal_footage",
  "title": "Meu bruto autorizado",
  "source_duration_seconds": 8,
  "source_asset": "camera",
  "revision": 1,
  "assets": [{"id": "camera", "kind": "footage", "path": "input/assets/meu.mp4",
              "rights": "owned", "rights_evidence": "captura própria autorizada pelo titular"}],
  "words": [{"word": "Omni", "start": 1, "end": 2}],
  "glossary": {"Omni": "OmniNexus"},
  "keep": [{"start": 1, "end": 3}, {"start": 5, "end": 8}],
  "beats": [{"start": 0, "end": 5, "speech": "OmniNexus; pausa sem fala",
             "elements": [{"kind": "caption", "position": "abaixo do rosto, dentro da safe zone", "word_index": 0}],
             "sound": "voz original; sem música"}]
}
```

Faceless usa `mode=faceless_montage` e assets autorizados de fotos/montagem; a
fonte temporal é a timeline de narração/roteiro. Sem voz, `words=[]` é válido.
Escolha explícita obrigatória, inclusive quando há footage auxiliar.

Tempos em segundos finitos. `keep` é cronológico, sem overlap e em velocidade
normal; omiti-lo mantém a duração inteira. Intervalos são [start,end). Cortes
podem remover palavras inteiras, nunca dividi-las. Reordenação, speed ramps e
crossfades com sobreposição exigem futuro contrato; não improvisar remapeamento.
Cada caption é derivada da palavra mantida e do glossário. Beats usam a timeline
**editada**. `word_index` ancora efeito na lista de captions remapeadas, dentro
do próprio beat. Material de elementos deve constar em `assets`; autorização
é declarada com evidência e revisada pelo humano, não comprovada pelo parser.
Caminhos são relativos: o planejador não lê arquivos nem valida symlinks; o
executor deve aplicar `resolve_within` ao materializar no workspace isolado.

Na revisão 2+, `previous_revision` deve apontar para a anterior. Isso registra a
linhagem, não faz backup por si só. Preserve fisicamente o artefato anterior.
Campos `approved`, `scheduled` ou `approver` do cliente não eliminam gates.
A aprovação final usa o contrato persistido de [release.md](release.md).
O endpoint sempre retorna `awaiting_beat_sheet_review` e `auto_queue=false` /
`auto_schedule=false`; apresentar a revisão ao Felipe é responsabilidade do
agente que chamou. Nenhum webhook/heartbeat/gate Telegram novo é criado.

Saída `workflow.entry_job_type` usa tipos atuais, sem migração de banco:

| mode | Primeiro job | Continuação |
|---|---|---|
| faceless_montage | social_clip | HyperFrames → ready_for_review → aprovação → draft → schedule |
| personal_footage | corte_bruto | corte_editorial → aplicar_corte_editorial → cortes_virais quando apropriado |

Depois de aprovação do beat sheet, o agente prepara a requisição existente de
criação com title/platform/width/height/duration_seconds no faceless; no bruto,
job_type=corte_bruto e source_path acessível ao worker. Não enviar o caminho
relativo do plano como se fosse um source_path já montado no container. Validar
o arquivo e a autorização no contexto real, sem buscar vídeo remoto.

Opcional `transcription={"engine":"whisper_local","model":"small"}` registra
seleção **local** explícita de modelo multilíngue; o exemplo não fixa o tamanho
do modelo para outros projetos. Default é `provided`, sem chamada externa.
`face_box={"x":0.3,"y":0.1,"width":0.3,"height":0.4}` configura região
normalizada, sem tracking; QA ainda deve revisar rosto/safe zones. Frame
sampling uniformemente distribuído tem teto de 80 frames; o planejador só
especifica a política, não extrai imagens. Elementos `kind=transition` podem
ter start/end editados dentro do beat: suas bordas não podem dividir palavras.
Overlap/transparência são itens de inspeção, não medições que este JSON comprove.

O mapa vale somente para os intervalos keep e a revisão informados. Se
corte_bruto remover silêncios, ou outra etapa cortar/reordenar, **não reuse**
este mapa como se ainda fosse válido: obtenha o mapa exato da nova etapa e
recalcule os tempos (ou transcreva a nova fonte autorizada e reinicie o plano).
Os executores legados não passaram a emitir mapas por esta mudança. Efeitos
não devem avançar com o mapa desatualizado. `time_map_scope` explicita essa
invalidação; rastreabilidade completa entre todos os cortes legados é trabalho
remanescente, não uma capacidade que o planejador alegue implementar.
