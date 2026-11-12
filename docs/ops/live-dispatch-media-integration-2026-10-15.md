# Integração local Live, mídia e fila — 15/10/2026

Branch `review/live-dispatch-ui-media`, base PR78 `3a282bd` preservada. Nenhuma mudança em main, imagem, serviço, conta, credencial, agente remoto ou publicação externa.

## Composição

- Continuidade: 0833a3c + 83f4e60 + 33d84de, da frente de memória.
- PR83 dispatcher: 26539e4, fila existente, binding de ownership, gates e idempotência.
- UI PR79/81: 75c643e, cb9d1ec, 6be8447, 3da6c77. Conflitos preservam VoicePicker, voiceId e composer isolado por empresa.
- Ponte UI/dispatcher: 198af01. Allowlist de request_internal_task/read_internal_task_status/cancel_internal_task. Modelo fornece apenas ticket/operação ou jobId; SDK fornece ID estável, closure injeta conversa/contexto. API revalida identidade.
- PR80: d9d0e37, 5e23ca0, 738b388, b4fc88d, 8fdc924, 7be44ee, 7bf9536, 2a3bd04. Tabelas Live e Gravações preservadas em conjunto, sem alterações de colunas antigas.
- PR84: ae394bb. Evidência TikTok inbox e YouTube privado/unlisted não conta como publicação pública; reconciliação não refaz upload/draft/schedule.
- PR76: b420164. Owner com heartbeat indisponível não bloqueia seleção dos seguintes; não reabre tickets.

## Limites e bloqueios

Continuidade e tarefas permanecem opt-in e desligadas na produção. As client tools não foram registradas no agente ElevenLabs remoto. Fluxo controlado usa socket/provider injetados e execução real da fila local; isso não comprova execução real de harness. Política efetiva sem ferramentas de CLI/MCP/plugins precisa de validação autorizada antes de habilitar.

Aprovação por voz continua contrato futuro. Publicação das imagens do PR78 continua aguardando autorização específica; autorização de conexão/plugin não substitui isso. Nenhuma tentativa de publicação foi feita nesta retomada.

Mensagem de coordenação à frente UI rejeitada pela revisão automática por ausência de autorização direta reconhecida para o destino. Sem retry ou outro canal. Integração do código existente e testes locais continuaram.

Acionador Instagram→Postiz não localizado nas fontes auditadas. Não equivale a inatividade global. Não criar watcher ou replay antes de identificar executor/configuração/cursor original.

## Validação

Primeira suíte integrada: 209 aprovados e 3 falhas no fixture TypeScript antigo, que não carregava novos módulos de continuidade. Corrigido o loader sem carregar SDK real. Após correção: 32 testes Live aprovados na revalidação; novo teste completo HTTP localhost aprovado separadamente. O controlador TypeScript real chama a API Flask, o worker local aplica provider injetado uma única vez para o ID repetido e o resultado aparece no estado do chat com link privado. Nenhum CLI ou modelo foi executado. Cinco testes JavaScript passaram; TypeScript, lint dos componentes alterados e build Vite passaram. O aviso de chunks maiores que 500 kB permanece. FFmpeg sintético e suíte media/orchestrator estão entre os 209 aprovados; codecs de celular físico, publicação e disponibilidade pública anônima não foram testados.
