---
name: mkt-creative-brief
description: "Planejar ou revisar briefing criativo de campanha, landing mobile, kit social e roteiro visual, com marca existente, hipóteses e provas. Para Mako, Pixel e Canvas quando o usuário pede criação, direção ou QA pertinente; mera menção a marketing não ativa."
metadata:
  author: OmniNexus; adapted from Open Design contributors
  version: "1.0"
---

> Modificado pelo OmniNexus em 2026-10-15: síntese textual em português; execução, defaults estéticos e integrações OpenDesign removidos. Copyright 2026 Open Design contributors. Apache-2.0; ver LICENSE e ORIGIN.md.

# Briefing e craft para marketing e criação

Leia [origem/licenças](ORIGIN.md), [exemplos](examples.md) e [QA](qa.md). Conhecimento textual descoberto no registro existente; não instala OpenDesign ou capacidades externas.

## Escopo e equipe

- Mako: oferta, público, campanha, três ângulos, CTA e evidências.
- Pixel: adaptação por canal, sequência de peças, legenda e área segura.
- Canvas: especificação visual, landing mobile e revisão de composição; não iniciar implementação de UI sem pedido específico.

Preservar a marca Sistema Britto existente: consultar `config/workspace.yaml` quando disponível, materiais aprovados do projeto e guia/voz acessíveis pelo mecanismo existente de conhecimento. Não inventar cores, fontes, logo, tokens ou regras de marca se a fonte estiver ausente. Registrar lacuna e usar placeholders descritivos; não criar novo design system nem migrar app. Não substituir identidade por um pacote de referência.

## Briefing antes das peças

Registrar objetivo, oferta, público, canal/formato, mensagem, CTA, prova disponível e restrições. Resolver paleta, acento, tipografia de corpo e destaque, layout, clima, densidade e exclusões. Cada decisão precisa de procedência explícita:

| Decisão | Valor | Procedência | Estado |
|---|---|---|---|
| <dimensão> | <valor ou pendente> | usuário / marca (caminho/versão) / hipótese | confirmado / validar |

Briefing incompleto: listar o que falta; propor hipóteses explícitas e reversíveis para avançar no plano, sem apresentá-las como preferência confirmada. Se faltar informação que muda a oferta, prova ou compromisso externo, manter essa parte pendente. Não aplicar silenciosamente a paleta/tipo padrão do upstream.

## Fonte única e craft

Reusar os tokens e orientações aprovados em sua fonte canônica real; registrar caminho, versão, origem e função. Uma tabela no briefing é referência, não uma segunda fonte de tokens. Não criar `manifest.json`, `tokens.css` ou `DESIGN.md` para substituir o sistema atual. Sugestões conflitantes ficam propostas para revisão.

Hierarquia: uma mensagem principal, leitura em ordem e CTA visível. Tipografia: famílias licenciadas já aprovadas, pesos com funções claras, tamanho/entrelinha adequados ao formato e idioma, espaçamento sem colisão; verificar quebras reais no mobile. Cor: funções consistentes, contraste e estados legíveis, não depender só de hue. Spacing: agrupar conteúdo relacionado e separar etapas. Justificar densidade e ornamentação pelo público, contexto e marca.

As preferências upstream sobre indigo, gradientes, emojis, fontes, número de acentos, simetria e cards não são proibições estéticas universais. Não impor essas regras sobre a identidade existente. Não afirmar que daemon/linter OpenDesign validou o material.

## Alegações e entregas

Toda métrica, depoimento, comparação e promessa factual exige fonte, período, contexto e autorização de uso quando aplicável. “10×”, “99,9%” e números sem fonte não viram claims. Remover ou marcar `[prova pendente — não publicar]`. Hipóteses de teste não são resultados; nunca inventar taxas, clientes ou depoimentos.

Preparar três ângulos de campanha, cada um com promessa sustentada, objeção, prova, CTA e risco. Landing e kit social seguem o mesmo brief, adaptando hierarquia ao canal sem mudar marca. Aplicar QA priorizado; declarar avaliações não realizadas e pendências.

## Vídeo e limites de ferramentas

Para pedido de roteiro visual, planejar cenas, início/fim/duração proposta, texto, asset e objetivo por cena. Primeiro aprovar/inspecionar o quadro estático e legibilidade; só então propor movimento que ajude a mensagem. Duração planejada não é duração medida. Este módulo não produz vídeo.

Sem renderizador disponível: entregar somente plano/storyboard e limites, com renderização, áudio, sincronia e inspeção visual marcados não realizados. Para produção efetivamente pedida, consultar o workflow HyperFrames local existente; esta skill não substitui suas regras nem promete ferramentas instaladas.

Ler esta skill não autoriza executar pacotes, scripts, daemon, comandos fora do sandbox, instalar app/dependências, acessar credenciais, gerar assets, publicar, enviar mensagens, gastar orçamento ou alterar UI/Live/VoiceDream. Não executar snippets upstream. As referências externas em ORIGIN.md não são competências instaladas. Publicação e alteração de marca exigem autorização própria.
