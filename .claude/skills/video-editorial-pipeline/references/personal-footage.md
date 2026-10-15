# Brutos pessoais

Mantenha a identidade, voz e intenção do Felipe. Transcrição palavra/início/fim
em JSON + glossário de marcas fornece âncoras; frames em pontos relevantes
mostram onde cabem legendas, memes e elementos sem tapar rosto/mãos importantes.

Crie rough cut com keep intervals inteiros, reveja a fala e remapeie cada palavra
para a timeline editada antes de posicionar legenda, música ou SFX. Não corte
respiração/pausa com um número fixo: compare clareza, naturalidade e propósito.
Use corte_editorial para proposta e aplicar_corte_editorial apenas após decisão
humana; corte_bruto faz a limpeza inicial existente. Não confunda as saídas
intermediárias com a versão final pronta para redes.

Correção de cor começa por exposição, balanço e consistência entre trechos;
reframe preserva rosto e gestos. Legendas respeitam safe zones do destino, com
revisão da grafia do glossário. Memes precisam de função editorial, tempo e
direitos verificados como qualquer mídia. Música baixa/ducking e SFX curtos
servem a fala; escute a prévia. Essas decisões são handoff para edição aprovada;
os endpoints atuais não executam color grading ou montagem de memes por
receber este contrato.

Preserve o bruto e cada versão anterior. Entregue prévia curta + snapshots e
peça comentários com timestamp **editado**, anotando também o trecho original
pelo time_map. Revise uma alteração por versão antes de solicitar aprovação
final e autorização específica de destino/horário.

B-roll/overlays entram **depois** do rough cut: não substituem corte,
re-enquadramento, escala ou legendagem completa. Configure face_box explicitamente
em coordenadas normalizadas e revise em frames amostrados ao longo do vídeo;
não é tracking. Contact sheet limitada a 80 frames precisa amostragem, não os
primeiros 80 frames. Verifique overlap, transparência e se transições dividem
palavras; export MP4 e alpha são entregas diferentes, a decidir no brief.

Não execute `transcribe.mjs` ou defaults de packs: uma chave ElevenLabs presente
pode selecionar nuvem contrariando a descrição. Se usar Whisper já disponível
localmente, escolha explicitamente `--engine whisper` e modelo multilíngue.
O contrato só registra `provided` ou `whisper_local`; não executa transcrição.
Não envie áudio privado a serviço externo sem autorização específica.
