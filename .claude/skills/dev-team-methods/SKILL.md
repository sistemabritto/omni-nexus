---
name: dev-team-methods
description: "Métodos seletivos para handoff aceito, contratos, debugging e revisão com evidência nos agentes existentes. Usar em tarefas de equipe/implementação/debugging/QA; não cria roster ou controlador e não autoriza execução externa."
metadata:
  author: OmniNexus; adapted from Agency Agents and Superpowers
  version: "1.0"
---

# Responsabilidades, handoff e verificação

Adaptação textual OmniNexus em 2026-10-15; fontes/autoria/licenças MIT em [ORIGIN.md](ORIGIN.md). Não instala Agency Agents ou Superpowers, ferramentas, skills globais ou controladores. Consultar apenas o módulo pertinente:

- Coordenação e responsabilidade: [papéis e handoff](handoff.md).
- Implementação, bug ou revisão: [execução/debugging/QA](debug-review.md), incluindo reuso e dívida deliberada.
- Criação/revisão visual no escopo: [complemento de crítica visual](design-critique.md), sem repetir o cookbook de design.

Mudança clara e limitada segue diretamente ao executor do fluxo existente; não exigir brainstorm/plano ou segunda aprovação só por este método. Feature que cruza módulos precisa de um plano único proporcional, interfaces, dependências e donos; aproveitar plano já existente, sem competir com ele. Os papéis abaixo são atribuições do registro existente, não novos agentes nem disparo automático de subagentes.

## Papel e leitura

| Agente real | Responsabilidade do método | Módulo |
|---|---|---|
| clawdia-assistant | Dono da fila operacional e handoff até aceite | handoff.md |
| helm-conductor | Respeitar coordenação/roteamento existentes; sem segundo controlador | handoff.md |
| compass-planner | Plano único quando interfaces/donos cruzam módulos | debug-review.md |
| bolt-executor | Contratos input/output, rastreabilidade, recuperação/idempotência | handoff.md, debug-review.md |
| hawk-debugger | Reproduzir, hipótese, regressão, fix mínimo, verificar | debug-review.md |
| mako-marketing | Hipótese de crescimento e critério de refutação | handoff.md |
| pixel-social-media | Roteiro/storyboard/repurpose com origem e direitos | handoff.md |
| nex-sales | Estágio CRM, evidência e próxima ação | handoff.md |
| dex-data | Taxonomia, dedup e reconciliação | handoff.md |
| lens-reviewer | Uma revisão de código com especificação e qualidade | debug-review.md |
| oath-verifier | Evidência independente de critérios e limitações | debug-review.md, design-critique.md |
| canvas-designer | Inventário de telas/estados, brief/provas e crítica responsiva | design-critique.md |

Preservar donos, escopo, marca, infraestrutura e permissões existentes. Nenhuma leitura autoriza envio, publicação, orçamento, automação, write em CRM/produção, merge/deploy ou alteração de Live/VoiceDream. Ferramentas só são capacidades reais quando disponíveis e utilizadas com evidência. Não instalar scripts/apps/MCP ou copiar comandos upstream.
