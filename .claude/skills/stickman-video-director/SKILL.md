---
name: stickman-video-director
description: "Direção opcional de vídeos com bonecos de palito: proposta, storyboard e prompts autocontidos. Usar quando o usuário pedir stickman/stick figure ou escolher esse estilo; não para qualquer vídeo genérico. Não renderiza nem chama Gemini."
metadata:
  author: OmniNexus; adapted from Stickman Video Director contributors
  version: "1.0"
---

# Direção de vídeos stickman — opcional

Copyright (c) 2026 Stickman Video Director contributors, MIT. Modificado pelo OmniNexus em 2026-10-15: adaptação textual PT-BR, sem defaults rígidos, assets ou integrações. Ver [origem e limites](ORIGIN.md).

Esta é habilidade de direção/storyboard/prompts, não renderizador, modelo de vídeo, API Gemini ou gerador de voz. Ativar apenas para pedido pertinente ao formato ou escolha explícita do usuário. Nunca transformar todo pedido de vídeo em stickman.

## Proposta

Ler a fonte e preservar significado, nomes e fatos verificáveis; não inventar estatísticas ou prometer retenção/completion. Responder e propor narração em PT-BR por padrão neste contexto, respeitando idioma solicitado. Inglês é opção para prompts conforme ferramenta escolhida; não é obrigação da narração.

Registrar fonte, público, mensagem, proporção, duração desejada, estilo/tema, personagens e restrições de marca. Perguntar lacunas que mudam o resultado; hipóteses reversíveis devem ser explícitas. Não arredondar duração silenciosamente: clipes de dez segundos são opção, não exigência. Duração total, número e extensão das cenas seguem o pedido e limites reais da futura ferramenta; sem ferramenta, são estimativas de planejamento.

Oferecer estilos quando necessário: minimalista claro/escuro, boneco em cenário de estúdio ou narrativo, desenho cômico e narrativa acolhedora. São direções possíveis, não presets instalados ou obrigatórios. Preservar direção visual e assets aprovados do Sistema Britto; não criar/trocar logo, fontes ou design system.

Criar proposta com título, mensagem, gancho, arco narrativo pertinente (por exemplo problema → ação → consequência), narração e perfil de voz proposto. Não forçar “segredos”, confronto ou pergunta de engajamento em toda história. Evitar adicionar fatos para tornar o gancho mais forte.

Storyboard: tempo inicial/final proposto, objetivo, quadro estático, ação concreta, câmera/transição, narração exata, áudio e continuidade. Primeiro validar composição e legibilidade do quadro estático. Planejar movimento pela função; não impor quatro efeitos por clipe ou mudança a cada dois segundos.

## Checkpoint e prompts

Apresentar a proposta atual e aguardar aprovação antes de escrever o pacote final de prompts. Mudanças globais em fonte, voz, duração, proporção ou estilo requerem proposta atualizada; não reutilizar aprovação de outra direção.

Aprovação criativa não autoriza custos, chamadas pagas, geração ou publicação.

Após aprovação, cada prompt é autocontido: proporção/duração pretendida, âncora completa do personagem e voz aprovados, cenário, ações em beats ajustados à duração, narração, câmera, estado inicial/final e restrições. Repetir a âncora relevante integralmente, não só “mesmo boneco”. Manter anatomia simples e coerente; garantir isso exige inspeção do material gerado, não só texto repetido.

Preservar posse de objetos, direção de deslocamento e transições entre cenas; mudanças de lugar/tempo devem ser intencionais. Voz pertence ao vídeo e não muda a cada cenário; perfil e narração são pedidos, não garantia de identidade sonora. Separar texto opcional de pós-produção dos elementos gerados; se legendas forem desejadas, planejar via workflow local de legendas.

Nomes de modelos, resoluções, FPS, duração exata e recursos citados por um prompt são especificações desejadas, não capacidades verificadas. Não afirmar suporte Gemini Omni Flash, voz consistente ou resultado 4K sem ferramenta conectada e evidência real.

## Limites da entrega

QA se houver material efetivamente gerado em tarefa autorizada: assistir vídeo para anatomia/continuidade, proporção, cortes e legibilidade; ouvir áudio para pronúncia, voz, cortes, música e sincronia. Comparar duração medida à proposta e inspecionar joins reais. Registro de prompt consistente não substitui essa inspeção. Marcar PASS/FAIL/NÃO TESTADO/NÃO APLICÁVEL com evidência. Legendas/overlays ficam na pós-produção solicitada.

Sem renderizador disponível: somente proposta/storyboard/prompts conforme etapa aprovada. Não declarar vídeo, áudio, sincronia, testes visuais ou consistência produzidos/verificados. Nenhum script, pacote, API, credencial ou chamada paga é habilitado por leitura desta skill. Não publicar nem gerar assets nesta integração.

Para produção efetivamente solicitada, ler o ponto de entrada local `.claude/skills-media/hyperframes/SKILL.md` e seguir seu workflow disponível; esta skill não contorna sandbox nem instala ferramentas. Entregar plano com limites se a produção não puder ser executada no ambiente autorizado.
