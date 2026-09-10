# Recuperação, VPS e Instagram — 10/09/2026

## Recuperação aplicada

Fonte: `otp_codes` anteriores a 10/09/2026. Consultados somente telefone, primeira ocorrência e data de consumo; nenhum código/hash/IP exportado. Plano privado 0600 em `tmp/legacy-lead-recovery-private.json`, fora do Git.

- 61 códigos, 45 telefones, 38 com verificação consumida; sete sem verificação excluídos.
- 37 leads ausentes restaurados no Supabase, um já existente. `created_at` mantém primeira ocorrência; `source=recovered-otp-unknown-origin`; `answers` registra lote, evidência e ausência de autorização de outreach. Não presumir campanha/aula de origem.
- 34 contatos já existentes no CRM receberam oportunidade de **revisão**, não qualificação comercial. Pipeline `f4b04a14-40a6-513e-be4f-b14cd4773312`, “Recuperação de leads · revisão”. Criados também 34 movimentos de entrada para manter histórico.
- Quatro telefones sem correspondência no CRM permanecem recuperados somente no site. Não houve criação de identidade/nome presumido.
- Checagem adicional das duas representações do nono dígito detectou uma identidade com dois contatos preexistentes e nenhuma oportunidade antiga. A oportunidade recuperada foi marcada `identity_review_required=true`. Não houve merge nem criação de outro contato para esse número.
- Nenhum contato/opção antiga de funil foi alterado. Não houve exclusão de dados ou envio de mensagem.

## Segurança e idempotência

- Primeiro executado com transações ROLLBACK nos dois bancos: 37/34 candidatos confirmados.
- Aplicação exige digest SHA256 do plano (`dab79ddd6a777557c9bb044d7b7753cf0c08f81c699b0777712a8715ca6d9ce7`).
- SQL de lote, `ON CONFLICT DO NOTHING`, checagem de oportunidade direta e via conversa, limites de lote/timeout. Sem mudança de schema ou RLS.
- Verificado que não há triggers SQL nas tabelas afetadas. Inserts no CRM evitam callbacks de aplicação que disparam automações/mensagens. Pipeline separado com regras de etapa vazias; registros indicam revisão manual.
- Rerun em ROLLBACK após aplicação retornou **0 inserts no Supabase, 0 oportunidades e 0 movimentos**.
- Consultas posteriores confirmaram zero lacunas no Supabase e zero oportunidades ausentes para os contatos cruzados.
- Script: `scripts/recover_legacy_leads.py`; cinco testes unitários passam.
- Banco do site e CRM não participam da mesma transação distribuída; reexecução idempotente recupera eventual falha parcial. Não chamar isso de fila contínua de reconciliação.

## Página /vps

Site commit `0c07aec`, Vercel success; testes complementares `53faa79`.

- Logo e visual escuro/lima do site; estrutura ilustrativa, benefícios com limites verificáveis.
- Preços/slugs mantidos: R$ 297 base, suporte adicional R$ 250, total R$ 547/mês.
- Retirados depoimentos sem origem comprovável no código e promessas absolutas de segurança, uptime e recuperação instantânea.
- Recursos de hardware/custo da infraestrutura aguardam confirmação do Felipe. Página orienta confirmar configuração antes de pagar; checkout continua acessível a quem já confirmou escopo.
- Falha do checkout agora mantém a página e apresenta erro inline; não redireciona silenciosamente para WhatsApp. Mensagem de WhatsApp usa quebras corretas e não copia PII de outro funil.
- Não envia e-mail como telefone. Não cria cliente/assinatura em teste real.
- Roteamento: aula para aprender; VPS para infraestrutura definida; sessão para definir problema, escopo e execução.
- Build passou; navegador 375/768/1440px: sem overflow, dois preços/slugs, UTMs, falha e retry; respostas de pagamento simuladas. Dois testes de oferta/WhatsApp passaram.

## Estratégia Instagram

Artefato: `assets/strategy/instagram-decisores-20260910.html`, copiado no Nexus para `workspace/strategy/[C]instagram-decisores-20260910.html`.

- Coleta atual Graph API: perfil 2.108 seguidores/43 posts; janela 11/08–10/09, America/Bahia: alcance 39.255, views 75.721, visitas ao perfil 1.239, interações 4.186.
- Insights por post são acumulados no instante de coleta; não somá-los como alcance único nem alegar que pertencem exclusivamente à janela.
- Comparação de quatro conteúdos com links e métricas; hipótese editorial, não causalidade ou qualificação de seguidores. Análise baseada em legendas/métricas, não transcrição integral de todos os vídeos.
- Nova bio preserva diagnóstico e resposta pessoal. Nome sugerido: Felipe Britto | IA para empresas. Bio, fixados e calendário ainda **não publicados**.
- Proposta: quatro posts/semana por duas semanas, conectando utilidade, diagnóstico e decisão; oito pautas com entrega e CTA congruente.
- Nenhuma rotina de direct, publicação ou edição do perfil foi executada.

Excluir lote de recuperação e QA das métricas de aquisição nova. Não tratar telefones verificados historicamente como autorização atual para campanha de mensagens.
