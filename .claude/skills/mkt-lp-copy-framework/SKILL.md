---
name: mkt-lp-copy-framework
description: "Framework de copy de alta conversão pra landing page/página de vendas, internalizado do repositório sistemabritto/lp-wizard (Squad Conteúdo: John Caples, Gene Schwartz, Robert Collier). 15 seções em ordem obrigatória, dos 3 cérebros (reptiliano → límbico → neocórtex), com o preço revelado só na seção 14 — nunca no hero. Use sempre que o usuário pedir 'revisar copy de página', 'landing page', 'página de vendas', 'melhorar conversão do site', 'a página tá fraca', ou pedir pra aplicar o 'framework do lp-wizard'. Aplica-se a qualquer página de oferta do Sistema Britto (Sessão de Start, Sprint, Implementação, Desafio) antes de qualquer redação nova ou revisão de copy existente."
metadata:
  version: 1.0.0
---

# Framework de Copy de Alta Conversão (lp-wizard)

Fonte: `github.com/sistemabritto/lp-wizard`, `.claude/skills/copy-framework/SKILL.md`
e `.claude/commands/escrever-copy.md`, internalizado em 11/09/2026. Uso interno
como framework de referência — sempre que uma página de oferta do Sistema
Britto for escrita ou revisada, aplicar esta ordem, não inventar uma nova.

## Quando usar

- Escrever copy nova para landing page/página de oferta.
- Revisar página existente que "está fraca" ou converte pouco.
- Usuário pedir explicitamente o framework do lp-wizard.
- Antes de qualquer redesign de UI numa página de venda — a copy vem primeiro,
  o layout serve a ela.

## Os 3 cérebros (ordem obrigatória)

| Cérebro | Ativado por | Função na copy |
|---|---|---|
| **Reptiliano** | Dor, medo, escassez, urgência, contraste brutal | Decide se fica lendo — milissegundos |
| **Límbico** | Histórias, identidade, raiva, esperança, pertencimento | Cria o desejo — segundos |
| **Neocórtex** | Dados, provas, garantias, lógica | Justifica a decisão já tomada |

**Erro fatal:** ativar o neocórtex primeiro. Ninguém compra por lógica —
compra por emoção e justifica com lógica depois.

## Erros que matam conversão

1. **Revelar demais** — curiosidade não satisfeita é o que sustenta a leitura;
   explicação completa cedo demais tira a razão de continuar.
2. **Culpar o leitor** — o problema é sempre de um inimigo externo (agência,
   ferramenta genérica, conselho ruim), nunca do leitor.
3. **Promessa genérica** — número específico e verificável converte; adjetivo
   vago não converte.
4. **Headline fraca** — a maior parte decide em segundos se continua lendo.
5. **Sem inimigo comum** — sem vilão externo não há tensão dramática.
6. **Sem garantia** — ausência de garantia é lida como risco, não como
   confiança implícita.
7. **CTA único** — no mínimo 3 ao longo da página: um de urgência (cedo), um
   de lógica (meio), um final (emoção + fechamento).
8. **Preço cedo demais** — regra específica de aplicação no Sistema Britto,
   confirmada em produção em 11/09/2026: mostrar o preço no hero ("R$150 de
   R$300") ativa o neocórtex antes de qualquer dor ou desejo terem sido
   construídos, e transforma a página inteira num anúncio de desconto em vez
   de uma decisão guiada. **O preço só aparece na seção 14 de 15** — nunca no
   hero, nunca junto da primeira dor.

## As 15 seções, em ordem obrigatória

| # | Seção | Cérebro | Função |
|---|---|---|---|
| 1 | Headline | Reptiliano | Para o scroll — promessa OU dor, nunca as duas, nunca revela o mecanismo |
| 2 | Dores (3 bullets) | Reptiliano+Límbico | Rapport — "é exatamente isso" |
| 3 | Vantagens de resolver | Límbico+Neocórtex | Visão do paraíso |
| 4 | Contexto da oportunidade | Neocórtex+Límbico | "Agora é a hora" |
| 5 | Raiz do problema | Neocórtex+Límbico | Reframe — a culpa é externa |
| 6 | Como a solução resolve | Neocórtex+Límbico | O mecanismo único |
| 7 | Intenções do criador | Límbico | Humanizar, criar confiança |
| 8 | Inimigo comum | Reptiliano+Límbico | Raiva canalizada num alvo externo específico |
| 9 | Custo da inação | Reptiliano | Medo da perda — temporal, real, nunca inventado |
| 10 | Outro lado da moeda | Límbico+Neocórtex | Contraste depois do medo |
| 11 | Prova visual | Neocórtex+Reptiliano | Evidência irrefutável — real, nunca depoimento fabricado |
| 12 | 1º CTA de urgência | Reptiliano | Escassez real (agenda, vaga, prazo) — ainda sem preço |
| 13 | As 3 partes (provocante / racional / misteriosa) | Límbico+Reptiliano+Neocórtex | Curiosidade final antes do fechamento |
| 14 | CTA final com preço + garantia | Reptiliano+Neocórtex | Conversão — é aqui que o preço aparece |
| 15 | Rodapé legal | Neocórtex | Credibilidade + conformidade (privacidade, termos) |

## Regras de escrita

- **Headline:** promessa OU dor, nunca as duas. Máximo ~12 palavras. Nunca
  revele o mecanismo (o "como", não o "o quê").
- **Dores:** situação específica + consequência vivida. Nunca genérico, nunca
  culpa do leitor.
- **Inimigo:** externo e específico (um padrão de mercado, não uma pessoa).
  Nunca concorrente pelo nome, nunca o próprio leitor.
- **Custo da inação:** temporal e visual. Amplifique o que é real — não
  invente número. Regra geral do workspace vale aqui também: sem dado
  inventado, ou nenhum dado (ver `esteira-de-conteudo.md`, `artifacts.md`).
- **Prova visual:** se não existe depoimento ou case real e autorizado pra
  essa oferta específica, mostre o entregável em si (o documento, a tela, o
  resultado concreto) em vez de fabricar prova social. Casos reais fechados
  do Sistema Britto (Laboratório de Insights, JURISMART, Voice Dream, Omni
  Nexus) podem ser citados como contexto, nunca inventados.
- **CTA:** primeira pessoa do comprador ("Quero..."), nunca "Clique aqui" ou
  "Comprar".
- **Provocante:** não entregue a resposta — só o suficiente pra criar desejo.
- **Misteriosa:** específico o bastante pra ser crível, vago o bastante pra
  criar necessidade. Nunca entregue o segredo.

## Squad de revisão (opcional, pra decisão colaborativa)

O lp-wizard roda a escrita como debate entre 3 personas — útil como checklist
mental mesmo sem multiplicar chamadas de modelo:
- **John Caples** (Executor) — escreve a primeira versão de cada seção.
- **Gene Schwartz** (Revisor) — questiona se a versão é persuasiva o
  suficiente, sugere reforço.
- **Robert Collier** (Supervisor) — aprova ou veta; vetada, John reescreve.

## Aplicado em produção

`sistemabritto.com.br/sessao-de-start` foi revisada com este framework em
11/09/2026 depois do preço aparecer "muito em cima" (no hero, junto da
escassez) — reordenada pras 15 seções, preço movido pra seção 14. Ver commit
no repo `sistemabritto/site`.

## Relacionado

- `social-editorial-strategy` — decide O QUÊ e PORQUÊ (Single Point of
  Belief, pilares); este skill decide a ESTRUTURA da página que vende.
- `mkt-quality-gate` — gate de qualidade geral de conteúdo; usar depois de
  aplicar este framework, não no lugar dele.
