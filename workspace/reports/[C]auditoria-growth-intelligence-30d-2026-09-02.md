---
title: Auditoria Growth / Revenue Intelligence — 30 dias
date: 2026-09-02
status: em_andamento
classification: interno
---

# Resumo executivo provisório

## Evidência

- A conta profissional `@sistemabritto` está conectada via Instagram Graph. O perfil retornado pela API é **Felipe Britto | Vibe Seller 🦈**, com a bio e o link `/links` coerentes com a nova tese.
- No recorte de 03/08 a 02/09, a API retornou 44 mídias: 42 Reels e 2 posts de feed. Para esse conjunto, retornou alcance agregado de **45.362**, 826 curtidas, 389 comentários, 768 salvamentos e 572 compartilhamentos.
- O Reel `DcpcV-kNq9k` (30/08) é o principal outlier observado: alcance 10.446, 247 curtidas, 237 comentários, 322 salvamentos e 262 compartilhamentos.
- O EvoCRM possui 75 conversas abertas, sem responsável: 50 WhatsApp e 25 Instagram. Há 34 conversas com mensagens não lidas, 38 sem primeira resposta e 21 cuja última mensagem é de entrada sem resposta.

## Diagnóstico inicial

O principal vazamento operacional comprovado não é falta de conteúdo: é a ausência de triagem, dono e SLA nas conversas que o conteúdo já está gerando. Há sinal comercial suficiente para priorizar revisão humana imediata, mas não há evidência de receita atribuída a Reel, pois o funil não preserva o vínculo mídia → CTA → conversa → negócio.

**Maior oportunidade (evidência):** instituir uma fila de resposta com responsável e SLA para as 21 conversas de entrada pendentes.

**Maior ameaça (evidência):** o conteúdo de melhor desempenho ainda promete ferramenta/CRM grátis. Isto pode atrair atenção de topo de funil sem demonstrar a tese de captura de valor, se não for conectado a diagnóstico, caso e oferta.

## Limites dos dados

| Campo solicitado | Estado | Motivo |
|---|---|---|
| plays, views, watch time, retenção, follows por mídia | NOT_SUPPORTED | Não vieram nos endpoints/permissões profissionais atualmente conectados. |
| profile visits, link clicks por Reel | NOT_AVAILABLE | A integração atual não retornou atribuição por mídia. |
| receita por conteúdo | NOT_AVAILABLE | Não existe join confiável entre ID de mídia, UTM/CTA, conversa e negócio. |
| conteúdo integral de DMs/WhatsApp | RESTRICTED | Auditadas somente por sinais e metadados; não expor em relatório compartilhável. |
| Agent Reach no Instagram | NOT_CONFIGURED | O plugin existe, mas requer OpenCLI + Chrome desktop autenticado; a VPS headless não é caminho suportado. |

# 1. Inventário de capacidades existentes

| Capacidade | Implementação nativa | Estado | Lacuna para Growth Intelligence |
|---|---|---|---|
| Social/Pixel | `.claude/agents/pixel-social-media.md`, Postiz e MediaJobs | Ativo | Pixel não fecha a correlação conteúdo → receita. |
| Instagram profissional | `.claude/skills/int-instagram/`, `dashboard/backend/routes/instagram.py` | Ativo | Métricas disponíveis são parciais. |
| Relatório social | `social-instagram-report`, `social-analytics-report`, `social-performance-analyzer` | Ativo | Não há auditoria composta de funil/CRM. |
| Reels externos | `ADWs/routines/custom/ig_reels_analysis.py` | Ativo para benchmark | É hard-coded para referência externa; não deve substituir insights da própria conta. |
| Vídeo | `ffprobe`, `ffmpeg`, `transcricao.py`, `vision_fallback.py` | Ativo | Faltava chave Groq no worker; corrigido em branch local. |
| CRM | `int-evo-crm`, EvoCRM | Ativo | Conversas abertas sem atribuição/SLA/dono. |
| Site/funil | site `pages/api/track.ts`, `pages/api/leads.ts`, `site_analytics.py` | Implementado | Credencial de analytics administrativo não está disponível no runtime atual. |
| Pesquisa externa | `plugins/reach` e avaliação do last30days | Parcial | Agent Reach requer desktop; last30days ainda não foi instalado por exigir revisão/consentimento de configuração. |

# 2. Reels: validação ponta a ponta

## Piloto — `DcpcV-kNq9k`

| Ficha | Resultado |
|---|---|
| Data/formato | 30/08/2026 · Reel |
| Duração/arquivo | 32,53s · H.264 720×1280, 24fps; áudio AAC 44,1kHz estéreo |
| Tema | CRM auto-hospedado/gratuito como alternativa a ferramenta paga |
| Hook visual | Headline na tela com promessa de CRM grátis nos primeiros segundos |
| Hook falado | Contraste entre CRM feito por criador e ferramenta comercial estabelecida |
| Estrutura | choque → contexto do problema → solução/GitHub → CTA por DM → pedido de engajamento |
| Formato | Talking head sobre captura de tela; demonstração e card de encerramento |
| CTA | Solicitar por DM o vídeo completo de instalação |
| Métricas disponíveis | alcance 10.446; curtidas 247; comentários 237; salvamentos 322; compartilhamentos 262 |

### Leitura editorial

**EVIDÊNCIA:** o Reel combina prova visual, uma dor econômica explícita e CTA de conversa; seus salvamentos e compartilhamentos são altos em relação ao conjunto observado.

**HIPÓTESE:** a promessa de custo evitado e a utilidade imediata explicam melhor o desempenho que o rótulo “CRM” isoladamente. É preciso comparar com amostra maior antes de afirmar causalidade.

**Como o reeditaria hoje:** manter a prova, mas trocar a promessa genérica “melhor CRM grátis” por “onde sua operação perde dinheiro com um CRM mal encaixado”; em seguida demonstrar a solução e oferecer diagnóstico/implementação, não apenas tutorial.

# 3. CRM e receita em risco

## Evidência operacional

| Indicador | Valor |
|---|---:|
| Conversas abertas sem responsável | 75 |
| WhatsApp / Instagram | 50 / 25 |
| Sem primeira resposta | 38 |
| Com mensagens não lidas | 34 |
| Última mensagem recebida sem resposta | 21 |
| Pendências classificadas P0 para revisão humana | 1 |
| Pendências P1 para revisão humana | 6 |
| Pendências P2 para nutrição/revisão | 14 |

Classificação é feita por sinais de intenção (preço, compra/link, demonstração/instalação, dor) e atraso; **não é prova de capacidade de pagamento nem autorização para contato**.

### Ação proposta, sem envio automático

1. **P0 — imediatamente:** revisar manualmente a conversa mais recente com múltiplos sinais de compra e atraso superior a 24h. A janela livre de WhatsApp deve ser verificada antes de qualquer resposta; sem janela, usar somente template previamente aprovado e adequado.
2. **P1 — esta semana:** atribuir dono às seis conversas com sinal de preço/compra e registrar estágio, oferta e próxima ação.
3. **P1 — esta semana:** definir SLA: nova entrada recebida → triagem em até 15 minutos no horário comercial; alerta em 1 hora; escalonamento em 24 horas.
4. **P2 — este mês:** separar conversas antigas de reativação das entradas recentes; não usar a base histórica como “lead quente”.

## Base histórica que não deve ser confundida com demanda nova

O pipeline `Leads do Site` tem 52 registros em `Novo Lead`, sem conversas vinculadas, em sua maior parte importados há cerca de 35 dias e associados a produtos históricos. Isto é um possível público de reativação, não evidência de intenção atual. Para WhatsApp, a classificação provisória é `TEMPLATE_NECESSARIO`/`INDETERMINADO` até checagem da última interação e do consentimento.

# 4. Site e posicionamento

## Evidência

- O repositório `sistemabritto/site` foi localizado e auditado em leitura. O `/links` já captura UTMs e eventos de CTA.
- Homepage, links e `llms.txt` ainda enfatizam automação, sistemas sob medida, CRM e ferramentas; não narram de modo consistente **Rastrear → Vibe Codar → Monetizar**.
- O site possui endpoints de tracking e leads, mas o acesso administrativo de analytics não está configurado no ambiente atual, impedindo reconciliação do funil no período.
- A auditoria de código identificou credenciais de integração EvoCRM codificadas como fallback em rotas de API do repositório. O valor não é reproduzido neste relatório. A remoção foi feita na branch `seo/vibe-seller-foundation`; a rotação do segredo exposto ainda é necessária antes de considerar o risco encerrado.

| Mensagem atual | Conflito | Impacto | Proposta | Prioridade |
|---|---|---|---|---|
| Automação/CRM/ferramentas | Pode reforçar perfil de “cara das ferramentas” | Médio | Explicitar oportunidade, valor capturado e casos | P1 |
| `/links` com múltiplas ofertas históricas | Dispersa a promessa dos Reels | Alto | Organizar por intenção: diagnóstico, prova/casos, implementação | P0 |
| `llms.txt` e metadados antigos | Diferenciam pouco a nova tese | Médio | Atualizar só após decisão de narrativa final | P2 |
| Fallback de credencial em rotas de API | Segredo pode estar exposto no histórico/código | Crítico | Rotacionar o segredo exposto e validar variáveis de ambiente em CI; fallback removido na branch `seo/vibe-seller-foundation` | P0 |

# 5. Arquitetura recomendada — nativa, sem novo agente social

## Decisão proposta

Não criar “novo social media agent”. Estender Pixel e as skills existentes com uma capacidade compartilhada de auditoria de growth.

1. Criar uma **skill compartilhada `growth-audit`** que orquestra fontes existentes (Instagram profissional, CRM, site analytics, rotinas de vídeo e git/VPS) e produz um pacote de evidências.
2. Criar um **command de leitura** equivalente a `auditar últimos 30 dias`, que recebe janela/escopo e chama a skill. Não publica, não envia mensagens, não cria tickets.
3. Evoluir a rotina de Reels existente para aceitar conta/intervalo e distinguir explicitamente benchmark público de própria conta profissional.
4. Permitir que Pixel consuma o relatório para priorização editorial; o CRM permanece dono de triagem comercial.
5. Somente após duas execuções manuais validadas, propor ADW mensal e card de dashboard. Não automatizar criação massiva de tickets.

# 6. Próximos passos de auditoria

| Prioridade | Entrega | Dependência | Critério de conclusão |
|---|---|---|---|
| P0 | Inventário e fichas dos demais Reels do período | download autorizado + orçamento Groq | cada campo ausente marcado com estado explícito |
| P0 | Revisão humana das conversas P0/P1 | responsável comercial; janela WhatsApp | dono, próxima ação e status registrados manualmente |
| P1 | Reconciliação site → CRM | acesso ao analytics administrativo do site | tabela de UTM/CTA/lead por período |
| P1 | Benchmark de mercado com last30days | instalação/configuração revisada e consentida | fontes, data, método e limitações registrados |
| P1 | Timeline engenharia/VPS e custo | logs/histórico já mapeados | linha do tempo e oportunidades de economia verificáveis |

# Apêndice: metodologia

- Janela: últimos 30 dias encerrados em 02/09/2026.
- Métricas de Instagram: API oficial autorizada, sem completar campos que a API não devolveu.
- Vídeo: URL autorizada da própria conta → `ffprobe` → extração de áudio → Groq Whisper → frames temporais, scene detection e contact sheet → análise humana/modelo de amostra; nunca todos os frames.
- CRM: chamadas REST somente de leitura. IDs, telefone, nomes e conteúdo não entram neste documento.
- Classificações e recomendações são rotuladas como EVIDÊNCIA, HIPÓTESE ou OPINIÃO conforme aplicável.
