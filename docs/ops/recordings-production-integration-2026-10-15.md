# Gravações / MediaRelease — integração sobre produção 7e84d6b

Este handoff descreve só a reconciliação e os novos testes/correções. O estudo e
escopo funcional continuam nas PRs56/72 e no handoff original de Gravações.

Branch: `fix/recordings-production-integration`. Base exata: `7e84d6b`.
Worktree de entrega: `task-3/recordings-integration`, limpa e reconciliada por
fast-forward com o ramo remoto. Durante a queda da execução elevada, o trabalho
continuou em `recordings-integration-local`, checkout temporário com Git gravável;
os commits foram depois transferidos para a worktree original, sem conflito pendente.

## Commits / fatias e dependências

| Commit | Fatia |
|---|---|
| e1fd2af | PR56: contrato editorial, conciliando CI existente |
| d37b0f4 | PR56: MediaRelease, preservando retry/migração/tema atuais |
| 77401c5 | PR72: fila Gravações, ACL, uploads e prévia |
| 4f2ac7b | Correção de duração de vídeo e proporção SAR + matriz de codecs |
| f541fd8 | Teste de handoff atualizado para exigir release vinculada |
| 8ed0726 | Compatibilidade de rollout: worker declara suporte recording_batch v1 |

As fatias são revisáveis separadamente, mas têm dependências: MediaRelease usa o
módulo editorial; Gravações usa MediaRelease. Não implantar a fila sem o guard de
capacidade e o worker correspondente. Não há diff de Live, sidebar ou stack.

O worker novo anuncia `recording_batch=v1` na listagem e no claim. Serviços
legados não recebem esses jobs; um claim sem a capacidade recebe409. Isso impede
que um worker antigo trate o tipo novo como social_clip e chame o gerador genérico.
Preferir construir/validar worker primeiro, depois dashboard; o guard também
mantém os lotes em fila caso a API seja atualizada antes do worker.

## Defeitos reproduzidos e corrigidos

- Vídeo sintético1,4s com áudio0,2s virava0,234s por `-shortest`. `apad` completa
  silêncio, com duração explícita do vídeo. Teste confere imagem até1,2s, tom no
  início e silêncio no fim; não estica fala.
- SAR2:1 era descartado ao fixar setsar após letterbox, deformando imagem.
  Agora o display aspect é normalizado antes do resize/pad. Pixels amostrados
  confirmam picture160×60 centralizado em160×240, sem recorte.
- Teste histórico de stack ainda permitia draft/schedule após approve legado.
  Agora exige release, digest humano e evidência por canal, preservando UTC por
  comparação temporal (formatos Z e .000Z são equivalentes).

## Codecs testados de verdade — apenas fixtures sintéticas locais

FFmpeg local6.1.1, sem render simulado nesses sete cenários:

| Cenário | Conferência |
|---|---|
| H.264 com áudio mais curto | Duração, pixels tardios e RMS de tom/silêncio |
| H.264 anamórfico SAR2 | Proporção e letterbox por pixels |
| HEVC Main10/hvc1 em MOV | Decodifica e normaliza H.2648bit + AAC estéreo48k |
| WebM VP9 + Opus | Mesma normalização e duração |
| MOV com matriz90° | Rotação aplicada uma vez e metadado limpo |
| H.264 VFR | Saída CFR30fps e duração |
| M4A AAC mono44,1k | Prévia preta finita e áudio AAC estéreo48k |

A matriz de rotação é escrita só na fixture sintética ISO-BMFF, sem depender de
-display_rotation (opção nova ausente em FFmpeg5). Não são capturas de celulares
físicos. HEIC, DolbyVision/HDR, perfis reais de iPhone/Android e limites do proxy
precisam de teste separado no ambiente de imagem final; não declaramos esses
formatos validados nem geramos mídia paga para testá-los.

## Verificação e ferramentas

- Regressão final: **151 testes passaram**, incluindo fila/ACL/worker, MediaRelease,
  retry, stack, sete cenários de codecs e testes de wiring/disabled de Live.
  Guard+retry também passou isolado em34 testes.
- TypeScript e build Vite passaram usando cópia local já existente do SDK
  @elevenlabs/client1.28.0. Sem npm install ou alteração de package/lockfile.
- Lint dos componentes RecordingsQueue e MediaReleasePanel passou. Media.tsx
  conserva seis erros de lint anteriores (any e setState em effect), sem mudança
  de Live para contorná-los.
- Graphify atualizado por AST, sem LLM.
- OpenCode1.18.18: alias real `drael/drael-v2` confirmado pelo próprio binário.
  Execuções de revisão selecionaram esse provider/model; a execução final usa
  variante low e small_model também Drael apenas via variável desta execução.
  Logs/cache temporários; defaults e credenciais globais intactos. Na primeira
  tentativa o título automático tentou o small_model omniroute do projeto, sem
  resposta; os runs seguintes fixam ambos em Drael. A última revisão encerrou
  após180s com exit124 e apenas step_start, sem texto. Não houve revisão Drael
  concluída; não atribuir os achados/correções deste handoff ao harness.

## Checklist para o único integrador

- [ ] Conferir base7e84d6b e conciliar avanço posterior de produção, sem reintroduzir
      botões legados de publicação nem perder retry/Live/tema atuais.
- [ ] Construir imagem worker e dashboard do mesmo ramo. Verificar FFmpeg da imagem
      final e rodar matriz sintética nela; não inferir cobertura de HDR/HEIC.
- [ ] Verificar guard: worker antigo não lista/assume recording_batch; worker novo
      lista e assume com capacidadev1. Não reativar jobs históricos.
- [ ] Aplicar apenas pelo integrador, com backup de SQLite/volume; tabelas novas,
      nenhuma exclusão/migração destrutiva. Grants devem ser explícitos por empresa.
- [ ] Testar celular físico, upload interrompido e codecs reais com mídia autorizada;
      fechamento → prévia → feedback versão → QA humano → MediaRelease.
- [ ] Distribuição real só com conteúdo, conta e horário especificamente autorizados.
      Nenhuma postagem/agendamento/deploy foi executado nesta preparação.
