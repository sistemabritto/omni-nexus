---
title: Briefs do roadmap 90 dias + mapa de links internos
date: 2026-09-02
status: proposta
classification: interno
depende_de: "[C]auditoria-editorial-blog-vibe-seller-2026-09-02.md"
---

# Parte 1 — Mapa de links internos

O blog tem **0 links internos em 76 artigos publicados** (evidência na
auditoria). Cada artigo é uma página órfã: o leitor que chega por busca lê e sai,
e o buscador vê 76 páginas soltas em vez de conjuntos sobre um assunto.

A proposta é hub-and-spoke por cluster, feita sobre o que **já existe**. Nenhum
artigo novo é necessário para executar esta parte.

## Clusters detectados no acervo atual

| Cluster | Posts | Hub proposto (o mais longo do cluster) |
|---|---:|---|
| whatsapp-operacao | 29 | `respostas-rapidas-whatsapp-business-exemplos-...` (2.158w) |
| conteudo-e-social | 11 | `relatorio-automatico-de-redes-sociais-ia-...` (1.947w) |
| leads-e-funil | 10 | `como-usar-segmentacao-de-leads-com-ia-...` (1.863w) |
| atendimento-e-chatbot | 7 | `quanto-custa-chatbot-de-ia-para-empresa-em-2026-na-pratica` (2.147w) |
| automacao-e-ferramentas | 5 | `make-e-zapier-para-empresas-qual-escolher-...` (2.116w) |
| infra-e-plataforma | 3 | `api-para-automacao-de-negocios-...` (1.852w) |
| crm-e-dados | 3 | `seguranca-de-dados-em-automacao-de-vendas-...` (2.479w) |
| sem cluster claro | 8 | redistribuir na revisão manual |

## Regras do mapa

1. **Cada spoke linka o hub do seu cluster**, uma vez, no corpo do texto, na
   frase que realmente pede. Nunca numa lista de "leia também" no fim: bloco de
   rodapé é ignorado pelo leitor e diluído pelo buscador.
2. **Cada hub linka de 3 a 5 spokes**, distribuídos ao longo do texto.
3. **Cada cluster linka o artigo âncora do seu pilar** (os 4 primeiros do
   roadmap), que é o que conecta o acervo à tese.
4. **Âncora descreve o destino em 2 a 5 palavras.** `ancora_util()` já derruba
   "clique aqui" e "saiba mais" em links próprios; a regra vale igual aqui.
5. **Sem link recíproco automático.** A ida hub→spoke e a volta spoke→hub são
   decisões separadas; forçar as duas cria pares que se linkam sem motivo.
6. **Teto de 4 links internos por artigo.** Acima disso o leitor para de clicar
   e o link vira ruído.

Volume estimado: ~29 links de volta (spoke→hub) + ~30 de ida (hub→spoke) + 8
para os âncoras de pilar. Trabalho de revisão de texto, não de reescrita.

## Ordem de execução sugerida

Do hub mais denso para o mais raro: `whatsapp-operacao` (29 posts) primeiro,
porque é 38% do acervo e concentra a maior parte da canibalização. Fazer esse
cluster já resolve a maior parte do problema.

---

# Parte 2 — Briefs do roadmap

Dez briefs, na ordem de prioridade da auditoria. **Nenhum foi publicado,
agendado ou criado como rascunho no Ghost.** Cada um segue o mesmo esqueleto,
que é o que `montar_prompt` agora consome.

Regra transversal a todos: nenhum número, cliente, depoimento, credencial ou
resultado pode ser inventado. Onde o brief pede dado que não existe, o campo
"Evidência necessária" diz de onde ele tem de vir antes do artigo existir.

---

## 1. Onde a sua operação perde dinheiro sem aparecer no caixa

- **Pergunta:** por que o resultado não melhora se ninguém está errando?
- **Intenção:** informacional com dor comercial. Topo qualificado.
- **Promessa:** ao fim, o leitor tem uma lista de onde procurar e uma conta que
  ele mesmo refaz com os números dele.
- **Tese:** vazamento de receita não aparece na DRE porque não é despesa, é
  ausência. Só aparece quando alguém procura por ele.
- **Outline (cada H2 é pergunta):** Por que o prejuízo invisível não entra na
  planilha? / Quais são os quatro lugares onde ele costuma estar? / Como medir
  cada um sem instalar nada? / Quanto custa cada dia sem medir? / O que fazer
  com o primeiro número que você achar?
- **Evidência necessária:** a conta de guardanapo (leads × taxa de resposta ×
  ticket) com variáveis, não com números fixos. Nenhum benchmark de mercado sem
  fonte linkada.
- **Fontes primárias:** as 75 conversas abertas sem responsável registradas na
  auditoria de Growth de 02/09/2026 servem de exemplo real da própria casa, se o
  Felipe autorizar citar.
- **Caso:** nenhum obrigatório.
- **Links internos:** hub de `atendimento-e-chatbot`, hub de `leads-e-funil`.
- **CTA / oferta:** `/sistema` — a call de 1h que produz o PRD.
- **Funil:** topo → meio. **Pilar:** RASTREAR. **Prioridade: P0.**

## 2. JURISMART: por que a diferenciação evaporou quando o ChatGPT popularizou

- **Pergunta:** como saber se o que você está construindo tem prazo de validade?
- **Intenção:** informacional / decisão estratégica. Meio.
- **Promessa:** um caso real de diferenciação comprimida, com o que daria para
  ter visto antes.
- **Tese:** produto cuja vantagem é "faz o que o modelo genérico ainda não faz"
  tem a validade do próximo release do modelo genérico.
- **Outline:** O que o JURISMART fazia e por que aquilo era valioso em 2023? /
  O que exatamente mudou quando o ChatGPT popularizou? / Que sinais existiam
  antes do prejuízo? / Como testar hoje se a sua vantagem é durável? / O que
  sobrevive à comoditização?
- **Evidência necessária:** só o que está em `memory/reference/vibe-seller.md`.
  **Nenhuma métrica de faturamento, usuários ou datas além do registrado.**
- **Caso:** JURISMART. Nome sempre JURISMART, nunca outro.
- **Links internos:** brief 5 (build ou buy), brief 8 (comoditização).
- **CTA:** `/sistema`. **Pilar:** CASE + MONETIZAR. **Prioridade: P0.**

## 3. Vibe Coder constrói, Vibe Seller monetiza: a diferença que decide o resultado

- **Pergunta:** o que é um Vibe Seller e por que saber construir não basta?
- **Intenção:** definicional. É a página canônica da tese e o principal alvo de
  citação por LLM.
- **Promessa:** definição autocontida, com a diferença operacional entre os dois
  papéis e o que cada um faz no dia a dia.
- **Tese:** construir ficou barato; achar o valor não capturado e capturá-lo, não.
- **Outline:** O que é um Vibe Coder? / O que é um Vibe Seller? / Qual a
  diferença na prática, num mesmo projeto? / O que conta como monetizar? /
  Por onde começa quem já sabe construir?
- **Requisito de GEO:** cada H2 abre com a resposta em uma frase, citável fora
  do contexto. É o formato que faz a LLM citar em vez de só indexar.
- **Evidência necessária:** a lista completa de formas de monetizar
  (receita, receita recuperada, conversão, economia, margem, automação,
  licenciamento, propriedade intelectual, equity, valuation, parceria,
  investimento) conforme a fonte de verdade.
- **Links internos:** todos os quatro âncoras de pilar apontam para cá.
- **CTA:** `/sistema`. **Pilar:** MONETIZAR. **Prioridade: P0.**
- **Observação:** este artigo justifica o hub `/vibe-seller` no site. Enquanto o
  hub não existir, o canônico é este post.

## 4. Laboratório de Insights: 70 usuários e por que isso não era um negócio

- **Pergunta:** usuário usando é a mesma coisa que negócio funcionando?
- **Intenção:** informacional / decisão. Meio.
- **Promessa:** o que separa tração de vaidade, contado por dentro de um produto
  que teve usuários e não teve negócio.
- **Tese:** retenção na renovação é o único teste; adoção inicial não é.
- **Outline:** O que o produto fazia e por que as pessoas entraram? / O que
  aconteceu na renovação? / Por que unit economics não fecha mesmo com uso? /
  Que pergunta teria antecipado isso? / O que eu faria diferente hoje?
- **Evidência necessária:** só "cerca de 70 usuários", "não sustentou unit
  economics" e "não reteve na renovação". **Sem inventar receita, churn, CAC ou
  data.**
- **Caso:** Laboratório de Insights.
- **Links internos:** brief 3, brief 7.
- **CTA:** `/sistema`. **Pilar:** CASE. **Prioridade: P0.**

## 5. Build ou buy: quando montar sai mais caro que assinar

- **Pergunta:** vale a pena construir isso ou pagar mensalidade?
- **Intenção:** comercial de decisão. Meio → fundo.
- **Promessa:** um critério de decisão que o leitor aplica ao caso dele hoje.
- **Tese:** o custo de construir é conhecido e único; o de manter é
  desconhecido e recorrente, e é ele que decide.
- **Outline:** O que entra na conta de construir? / O que entra na conta de
  manter, que quase ninguém soma? / Quando assinar é claramente melhor? / Quando
  construir vira ativo em vez de custo? / Como decidir sem depender de quem
  vende a resposta?
- **Evidência necessária:** estrutura de custo em variáveis. Preço de ferramenta
  citada só com link para a página oficial de preço.
- **Links internos:** brief 6, hub `automacao-e-ferramentas`, hub
  `infra-e-plataforma`.
- **CTA:** `/sistema` para escopo; `/vps` quando a conclusão for infraestrutura.
- **Pilar:** VIBE CODAR. **Prioridade: P0.**

## 6. Quanto custa manter de pé o que você automatizou

- **Pergunta:** e depois que estiver funcionando, quanto isso custa por mês?
- **Intenção:** comercial de investigação. Meio.
- **Promessa:** a conta que os tutoriais não fazem.
- **Tese:** 19 dos artigos deste blog ensinam a montar; nenhum ensinava a
  manter, e é na manutenção que a automação vira custo escondido ou margem.
- **Outline:** O que quebra e com que frequência? / Quanto custa cada camada
  (infra, modelo, integração, pessoa)? / Como saber se está caro? / O que dá
  para desligar sem perder resultado? / Quando o custo de manter mata o ganho?
- **Evidência necessária:** custo de token e de VPS com fonte linkada, na data.
- **Links internos:** brief 5, hub `infra-e-plataforma`.
- **CTA:** `/vps`. **Pilar:** VIBE CODAR. **Prioridade: P1.**

## 7. Como transformar automação em margem, não em custo escondido

- **Pergunta:** automatizei e não vi diferença no resultado. Por quê?
- **Intenção:** comercial. Meio → fundo.
- **Promessa:** o caminho de automação até a linha de margem, com o que precisa
  ser medido antes e depois.
- **Tese:** automação que não muda uma linha do P&L é hobby caro.
- **Outline:** Por que economia de tempo não vira dinheiro sozinha? / Qual linha
  do resultado cada tipo de automação toca? / Como medir antes para poder
  comparar depois? / O que fazer com o tempo liberado? / Quando a automação
  aumenta custo?
- **Links internos:** brief 1, brief 6, hub `automacao-e-ferramentas`.
- **CTA:** `/sistema`. **Pilar:** MONETIZAR. **Prioridade: P1.**

## 8. O risco de comoditização: a sua solução tem prazo de validade?

- **Pergunta:** o que eu construí vai continuar valendo daqui a um ano?
- **Intenção:** informacional / estratégica. Meio.
- **Promessa:** um teste de defensabilidade aplicável em uma tarde.
- **Tese:** se a vantagem é capacidade técnica, ela expira; se é distribuição,
  dado próprio ou encaixe operacional, ela dura mais.
- **Outline:** O que a IA comoditizou nos últimos dois anos? / Que tipos de
  vantagem sobrevivem? / Como testar a sua em cinco perguntas? / O que fazer
  quando a resposta é ruim? / Vale construir mesmo assim?
- **Caso:** JURISMART, como ilustração, com link para o brief 2.
- **Links internos:** brief 2, brief 3.
- **CTA:** `/sistema`. **Pilar:** MONETIZAR. **Prioridade: P1.**

## 9. Como monetizar tecnologia com equity em vez de mensalidade

- **Pergunta:** dá para ser sócio do resultado em vez de fornecedor?
- **Intenção:** informacional / estratégica. Meio.
- **Promessa:** os formatos reais de captura de valor além da assinatura, e
  quando cada um faz sentido.
- **Tese:** vender software é um dos modos de capturar valor, e frequentemente
  o pior deles para quem constrói rápido.
- **Outline:** Quais são os formatos além de mensalidade? / Quando equity faz
  sentido para os dois lados? / O que precisa estar escrito antes? / Quais são
  os riscos de virar sócio de operação alheia? / Como escolher entre serviço,
  licença e participação?
- **Evidência necessária:** sobre Voice Dream, apenas o que está registrado como
  informado pelo fundador. **Sem projeção de valuation.**
- **Caso:** Voice Dream.
- **CTA:** `/sistema`. **Pilar:** MONETIZAR. **Prioridade: P2.**

## 10. Omni Nexus por dentro: o sistema que escreve este blog

- **Pergunta:** o que dá para operar sozinho com agentes, de verdade?
- **Intenção:** informacional / prova. Atravessa o funil.
- **Promessa:** build in public verificável, incluindo o que não funcionou.
- **Tese:** o blog que o leitor está lendo é a saída do sistema descrito no
  artigo, e os erros dele estão documentados.
- **Outline:** O que o sistema faz sem intervenção? / Onde ele para e espera
  humano, e por quê? / O que já quebrou em produção? / Quanto custa rodar? /
  O que eu não automatizaria de novo?
- **Evidência necessária:** aprovações humanas em gate, incidentes já
  registrados nas rules. **Sem custo mensal sem número verificado.**
- **Caso:** Omni Nexus.
- **CTA:** `/sistema`. **Pilar:** CASE. **Prioridade: P2.**
- **Cuidado:** este artigo expõe arquitetura interna. Revisar o que é público
  antes de escrever, e nunca citar host, token, nome de serviço interno ou
  caminho de arquivo.
