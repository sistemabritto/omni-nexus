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
approve/create-draft/schedule; não muda a máquina de estados nem os controles
de publicação existentes.

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
- [ ] Aprovação final do Felipe antes de qualquer draft/agendamento; destino e
  horário autorizados explicitamente. Registrar confirmação no sistema de destino.

Nenhuma geração paga, instalação de repositórios, envio de áudio privado,
credencial alterada, publicação ou agendamento real. OpenCode/Claude Code não
invocados; Drael não selecionado e defaults globais não alterados. Sem deploy próprio.
