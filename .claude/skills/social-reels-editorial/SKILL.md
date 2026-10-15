---
name: social-reels-editorial
description: "Método editorial PT-BR para Pixel e coprodutor de Reels: três ganchos, roteiro, texto na tela/beat sheet, legenda/CTA e reaproveitamento de bruto. Não renderiza/publica e não prevê viralidade."
metadata:
  author: OmniNexus; adapted from Jake Schincariol
  version: "1.0"
---

# Reels — apoio editorial ao coprodutor

Copyright (c) 2026 Jake Schincariol, MIT; adaptado pelo OmniNexus em 2026-10-15. Ver [origem e limites](ORIGIN.md). Nenhum script, plugin completo, renderizador ou integração externa foi instalado.

## Aplicação e contrato existente

Usar quando houver pedido de roteiro/gancho/legenda/repurpose de Reels, ou no coprodutor existente. Preservar marca e voz Sistema Britto, banco de ganchos, matriz de temas, fase de funil e iscas/CTA do protocolo local. Não usar exemplo de história/receita de outro criador como experiência do fundador. Contexto desconhecido fica hipótese explícita ou dado pendente.

**Modo coprodutor in-process:** o handler continua recebendo UM roteiro no JSON estrito já definido. Não acrescentar chaves, texto fora do JSON ou múltiplos objetos; obedecer hint do criador, campos, duração aproximada e limite de palavras do contrato existente. Preparar três candidatos de gancho e escolher um para `hook_spoken`/`hook_visual`; preservar uma saída final. Incluir apenas notas essenciais de beats/texto na tela em `script_md` se couberem no contrato, sem substituir narração por instruções de produção. Alternativas detalhadas, legenda e plano expandido pertencem ao pedido editorial em conversa, não a campos inventados do handler. A revisão humana existente decide o criativo; esta skill não cria checkpoint paralelo.

**Modo Pixel/conversa:** apresentar três opções de gancho falado e texto de abertura, diferentes em mecanismo, com razão ligada à ideia e prova; recomendar pela clareza/fidelidade, sem score numérico de viralidade. Desenvolver a opção escolhida ou a direção já autorizada pelo usuário e oferecer ajustes.

## Método editorial

1. Fonte e objetivo: ler material disponível, identificar público, fase do funil, uma ideia central, prova real e próxima ação. Se há informação insuficiente, apontar a lacuna; não preencher com número/depoimento inventado.
2. Três ganchos: específicos e verdadeiros, prometendo apenas o que o vídeo entrega. Distinguir fala e texto visual. Avaliar entendimento, relevância, sustentação e payoff com checklist qualitativo. Nenhuma fórmula escolhe vencedor.
3. Roteiro: PT-BR falável, voz aprovada e frases que o criador consegue dizer naturalmente. Corpo resolve a promessa e leva ao CTA compatível com oferta/isca real. Não forçar loop ou efeito que prejudique sentido.
4. Texto na tela e beat sheet: quando solicitados em formato expandido, tabela com início/fim estimados, intenção, fala, texto visual, ação/asset e transição. Estimativa não é duração medida; leitura cronometrada ou áudio real é necessária para validar. Texto curto/legível e áreas seguras verificadas no formato/preview vigente, sem coordenadas universais presumidas.
5. Legenda e CTA: contexto que complementa vídeo, termos naturais e uma ação principal com destino/entrega verdadeiros. A prévia/truncamento/limites e hashtags dependem da interface atual; não tratar “125 caracteres” ou uma regra de hashtag upstream como contrato permanente sem verificar. Não alterar palavra/isca definida no protocolo local.
6. Repurpose de bruto: ler transcrição inteira acessível e extrair unidades autônomas (história, mecanismo, erro, afirmação sustentada). Registrar arquivo/URL, timecodes reais ou aproximados explicitamente e direitos. Não inventar timestamps se só há texto. Selecionar formato por ideia; não prometer semana de posts se o bruto não sustenta. Aproveitar footage próprio autorizado preservando contexto, sem cortar para inverter sentido. Reaproveitamento proposto não equivale a corte/render realizado.

## Revisão humana e produção

A entrega aqui é editorial. Preservar contrato de produção `.claude/skills/social-media-production/SKILL.md`: o job/worker existente é dono de render, validação e publicação; não rodar comandos dele nem acessar Postiz. Aprovação humana deve corresponder à versão/hash do asset, copy/legenda/CTA, canais e calendário efetivamente revisados pelo mecanismo vigente. Mudança nesses itens exige reconciliação/nova aprovação conforme o fluxo existente; não fabricar hash, aprovação ou status de publicação.

Aprovação criativa não autoriza upload, campanha OpenReply, Postiz, comentário, DM, custos ou publicação fora do fluxo já autorizado. Esta skill não chama handlers de geração/tick/mirror nem cria automação; a integração só adiciona instrução ao passo LLM já existente. Não instalar CLIs/apps ou ler credenciais/arquivos globais de voz por obrigação upstream.

## QA e medição honesta

Sem renderizador/material produzido, indicar vídeo, áudio, sincronia e legibilidade real como NÃO TESTADOS. Se uma tarefa autorizada produzir mídia, observar vídeo/áudio reais, cortes, captions, voz e CTA antes de declarar revisão. Scripts não avaliam qualidade estética ou “humanidade”. Não remover Unicode/acentos PT-BR automaticamente.

Hookscore tem limitação admitida pelo autor (AUC 0,56 na comparação de hits/misses do corpus dele); isso não valida previsão de vencedor em Reels/PT-BR. Usar checklist de clareza, não nota viral ou promessa “indetectável”. Não transplantar scripts com contagem/CTA em inglês/ASCII, parsers de números abreviados e baseline de auditoria inadequados.

Medição: ligar criativo/campanha/hipótese a leads qualificados, oportunidades e vendas no CRM, com janela/coorte/denominador e dedup; views/retenção são sinais de atenção e não prova causal de receita. Números abreviados ambíguos e baseline faltante ficam indisponíveis até validação; não inventar múltiplos de viralidade ou desempenho.
