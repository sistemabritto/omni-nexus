# Revisão criativa de vídeo — versão renderizada

Complemento original OmniNexus, 16/10/2026, aos métodos locais Anti-Slop e Taste
atribuídos nos ORIGIN/LICENSE existentes. Não instala os projetos upstream e
não transforma heurística de UI em certificado audiovisual.

Ler o conteúdo de `.claude/skills/design-quality/SKILL.md`,
`.claude/skills/design-quality/review.md` e
`.claude/skills/dev-team-methods/design-critique.md` antes da revisão pertinente.
Marca/aprovação do Sistema Britto e objetivo da peça prevalecem sobre gosto
estético genérico; não trocar identidade, impor bans ou adicionar efeitos por quota.

## Revisar a mesma versão

Oath responde pela revisão independente da criação. Probe pode fornecer medidas
e verificações técnicas; Zen limpa código, não substitui julgamento audiovisual.
O revisor precisa do render real, versão/hash, duração medida, roteiro/brief e
fonte/versão da marca aprovada. Preview, roteiro, ffprobe ou checklist do criador
não comprovam que o vídeo completo foi visto/ouvido pelo revisor.

Inspecionar os frames relevantes e reproduzir o material no contexto da entrega;
se amostrar uma VSL longa, registrar os intervalos cobertos e os não inspecionados.
Não declarar o restante revisado. Registrar defeitos antes de pedir aprovação ao
Felipe. Alteração de render/hash invalida a revisão anterior; retestar correções
na nova versão, sem copiar o PASS antigo. Revisão humana do beat sheet não é
aprovação do render final.

| Critério | Observação efetiva exigida |
|---|---|
| Identidade | Comparar fontes, cores, logo, voz/claims e composição com brief/marca aprovados, indicando fonte/versão; fonte ausente é pendência |
| Legibilidade | Ver texto e gráficos em tamanho de consumo, safe zones, reflow/crop e contraste real; cálculo opaco isolado não prova frames com imagem/alpha |
| Composição | Hierarquia, foco, rosto/elemento principal, posição de overlays e prova das alegações; não avaliar por gosto ou número de cards |
| Ritmo | Ouvir/ver desenvolvimento, pausas, densidade de narração/texto e payoff; não impor corte a cada N segundos |
| Transições | Continuidade e joins, sem palavras cortadas, salto acidental ou movimento sem função; observar reduced motion quando pertinente ao destino |
| Legendas | Sincronia, grafia/glossário, quebras, tempo de leitura e colisões nos frames; ausência aprovada pode ser não aplicável com motivo |
| Áudio | Ouvir fala/pronúncia, clipping, mix/ducking, música/SFX e joins; ffprobe não ouve nem verifica licenças de trilha |

Para cada critério: PASS/FAIL/NOT_TESTED/NOT_APPLICABLE, observação específica,
referências locais de frame/artefato ou intervalo temporal e hash da evidência.
Não fabricar evidência ou preencher PASS por herança. Sem render/áudio acessível,
registrar NOT_TESTED. N/A exige justificativa no escopo; identidade não fica isenta.
Achados têm critério, severidade P0/P1/P2, localização/impacto e correção; resolvido
exige registro do reteste na versão atual. P0/P1 abertos ou critérios não testados
impedem a elegibilidade para aprovação. P2 permanece visível à decisão humana.

Contrato puro: `dashboard/backend/media_creative_review.py`, documentação em
`docs/agents/creative-review-contract.md`. Validação de JSON é apenas estrutura
e vínculo de hash/versão. O servidor precisa conferir evidências locais, duração,
identidade/independência do revisor e persistência; um payload do cliente não é
prova de revisão. Oath não autoaprova a peça que criou. O gate de publicação e a
sessão humana de aprovação existentes continuam responsáveis pela ação externa.
