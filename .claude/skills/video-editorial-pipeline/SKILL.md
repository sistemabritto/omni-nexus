---
name: video-editorial-pipeline
description: Planejar e revisar vídeos faceless com fotos/montagem/overlays ou edição de brutos pessoais no OmniNexus, com mapa temporal, beat sheet e aprovação do Felipe antes de agendar. Use na preparação editorial ou handoff para os MediaJobs existentes.
---

# Edição com referências aplicáveis

Escolha explicitamente um formato: `faceless_montage` ou `personal_footage`.
Não deduza faceless só por ausência de rosto, nem transforme bruto pessoal em
avatar. Pixel (`.claude/agents/pixel-social-media.md`) conduz o plano editorial;
Bolt (`bolt-executor.md`) implementa somente a edição aprovada; Probe
(`probe-qa.md`) verifica resultado. São papéis dos agentes existentes, não novos
heartbeats. Não acione `reels-copilot` nem suas campanhas/iscas para editar um
bruto: esse agente já tem outra responsabilidade.

## Planejar antes de executar

**Contexto de worker isolado:** se esta skill for lida dentro de um job já
criado, não use SDK/API, não crie jobs e não procure credenciais. Leia somente
os artefatos locais do plano aprovado e a referência de execução pertinente.
Se um job que explicitamente pede este novo fluxo não incluir a decisão de
revisão do beat sheet nos seus insumos, reporte a falta ao orquestrador; não
invente aprovação. O planejamento abaixo pertence à sessão do agente com o
Felipe, antes da submissão, não ao subprocesso de composição.

Use o SDK `evo.post('/api/media/editorial/plan', payload)` para obter um plano
validado, sem enfileirar. O contrato e os campos estão em
[references/contract.md](references/contract.md). A resposta contém job type,
etapas existentes, mapa fonte→editado, legendas remapeadas e gates. O endpoint
exige permissão execute; não recebe aprovação válida por flags do cliente.
Erros de corte dentro de palavra, fonte não autorizada ou tempos inválidos
precisam ser corrigidos antes da revisão.

Apresente ao Felipe o beat sheet com tempos **editados**, fala, elemento,
posição e som. Inclua miniatura/frames para decidir espaço visual e inventário
de materiais autorizados. Peça a aprovação concreta desse plano na conversa
existente; o endpoint responde `awaiting_beat_sheet_review`, não envia card nem
considera esse JSON uma aprovação. Não crie jobs enquanto faltar essa decisão.

Após aprovação, crie apenas o job correspondente à primeira etapa suportada via
`POST /api/media/jobs`, mantendo os gates das etapas seguintes. O plano é um
handoff, não um executor novo de color grading, memes ou efeitos. Para produção,
revalide o volume compartilhado e as correções de manifesto/retries (PR32/PR53).

- Faceless: leia [references/faceless.md](references/faceless.md).
- Bruto pessoal: leia [references/personal-footage.md](references/personal-footage.md).
- Consulte [references/sources.md](references/sources.md) quando usar uma referência;
  as fontes sugerem decisões, não autorizam copiar código, clipes ou mídia.

## Revisão que fecha o ciclo

Faça rough cut primeiro, sem dividir palavras; compare o mapa de tempos com a
transcrição. Só depois acrescente efeitos ligados a palavras/ideias específicas.
Não use thresholds de pausa ou zoom como regra universal. Preserve versão
anterior e registre revisão por timestamp e revisão/ID do artefato. Gere uma
prévia curta representativa e snapshots antes do render completo autorizado.

Probe verifica áudio (inteligibilidade, clipping, música baixa/ducking e SFX
pontuais), legendas (sincronia e glossário), rosto (sem crop/overlay indevido),
safe zones da plataforma e direitos de todo material, inclusive memes. Para
faceless, marque face como não aplicável com justificativa, sem inventar rosto.
QA não é só ffprobe: mantenha a inspeção audiovisual humana e registre achados.

Entregue vídeo e evidências para revisão do Felipe. `ready_for_review` não é
aprovação. Para a aprovação final vinculada ao hash/versão do render e à
copy/conta/calendário de cada rede, siga [references/release.md](references/release.md).
O registro persistido exige digest atual e sessão humana; alterações invalidam
a aprovação. O adapter mantém ID, estado, URL e checkpoints por canal, sem
recriar posts em resultados ambíguos. Os endpoints antigos de draft/schedule
retornam 409 para impedir atalho sem essa vinculação.

O planejador editorial nunca distribui automaticamente. Não trate aprovação do
beat sheet como aprovação final ou autorização de agendamento. Não gere mídia
paga, instale repositórios, altere credenciais ou publique como consequência da
leitura desta skill.
