# Contrato de revisão criativa vinculada ao render

Módulo puro `media_creative_review.py`, sem DB, rede, arquivo, modelo ou render.
`validate_creative_review(payload, *, render_sha256, version_id)` normaliza ou
levanta ValueError. `creative_review_eligible(normalized)` não concede aprovação.

Campos obrigatórios e exclusivos:

- `render_sha256`: digest lowercase64, comparado ao valor esperado do servidor.
- `version_id`: string, comparada ao ID esperado, não só um nome de arquivo.
- `duration_seconds`: número finito positivo; caller confere com duração real.
- `brand_reference`: `{source, version}` da fonte aprovada; existência/aprovação não são certificadas pelo parser.
- `methods`: objetos `anti_slop` e `taste`, cada qual `{source, version, application}`. Fontes/pins locais são constantes METHODS; `application` explica como os critérios foram usados no render, não só o nome do método.
- `criteria`: exatamente identity, legibility, composition, rhythm, transitions, captions, audio. Cada item `{status, observation, evidence, reason}`.
- `findings`: lista `{id, criterion, severity, status, description, resolution, evidence}`; IDs únicos, severidade P0/P1/P2, status open/resolved.

Status: PASS/FAIL exigem evidência; NOT_TESTED/NOT_APPLICABLE exigem motivo.
Observação é texto específico da versão. Cada evidência tem
`{kind, ref, sha256}`; kind é frame/artifact/time_range/audio_range, e intervalos
acrescentam start/end, com 0≤start<end≤duration. Ref é caminho relativo local,
sem URL, traversal ou caracteres de controle. Sha é lowercase64. Nenhum path é
aberto pelo validator. Resolução de achado exige texto e evidência de reteste.

Elegibilidade: identidade PASS; demais critérios PASS ou N/A fundamentado;
nenhum P0/P1 aberto. P2 fica visível à decisão humana. Review FAIL/NOT_TESTED
pode ser persistida, mas não habilita aprovação. Nenhum campo reviewer,
approved ou eligible do cliente é aceito.

O endpoint integrador precisa derivar reviewer da sessão, exigir independência
do criador, verificar acesso e conteúdo/hash dos refs dentro do workspace
correto, checar duração real, CAS/version/hash atuais e persistir antes do gate
humano. Arquivo/render alterado invalida a revisão. Referência/JSON não são
prova de observação: registrar reprodução/inspeção efetiva e limitações. Não
conceder acesso externo, modificar ACL ou liberar publicação com base no payload.
O hook de servidor é implementado pela frente de vídeo, não por este módulo;
sem ele, este documento é contrato verificável, não gate produtivo instalado.

A mesma trilha serve modos combináveis e VSL/mini-VSL motion. Fonte, método,
rights/brand e QA pertencem à versão, não a um selo genérico do agente. Exemplo
sintético em `evidence/creative-review-fixture.json`: demonstra estrutura e não
comprova que vídeo real foi revisado.
