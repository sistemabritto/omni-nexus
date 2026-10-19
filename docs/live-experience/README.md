# Live: composição revisada

Base do dashboard: `a57dff8694ae11dfc5deec182dea8575d3fe0c40`, já online, cujo pai é a produção histórica `120982837916464ea8f0f12ee56dbc62ca219f38`. Nenhum merge do pacote misturado. O runtime é uma composição independente sobre `7f2bb2a204558a80ad0468abe1f642831099d773`, SHA realmente instalado no scheduler.

## Experiência

Live reúne seleção dos 12 agentes, waveform circular de áudio real e conversa com Markdown, copiar, links e anexos textuais. Conectar por voz pede microfone no clique inicial; pausar o microfone mantém a saída de áudio. Trocas explícitas e via ferramenta revalidam ACL/manifesto e mantêm a conversa lógica, com aviso visual e textual. Vozes distintas são defaults por persona; preferências salvas e reset explícito são respeitados. A configuração fica na página do agente. Rotas usam os nomes atuais, preservando query/hash nas antigas. O catálogo `/agents` e `/agentes` redireciona para `/live`; não existe item Agentes na sidebar e Materiais pertence a Inteligência.

## Capacidade real

- Skills/integrações: descoberta sem credenciais e leitura de documentos como referências não confiáveis. Configurada não significa saudável, nem código executado.
- Artefatos: documentos textuais e SVG estático, com links privados ao usuário/empresa. Upload txt/md/csv/json, sem formulário de caminho de Workspace na página Live.
- Imagens: OpenAI existente, `gpt-image-2`, PNG, qualidade medium, uma saída. Reserva persistida impede repetição por requestId; processamento é assíncrono e não recupera/reenvia automaticamente após perda do worker. Timeout fica incerto. Não há geração paga durante QA.
- Vídeo: entrada restrita na fila de mídia já existente, sempre draft; nenhuma publicação/agendamento ou mudança de worker.
- Áreas do menu: consultas por adapters nomeados, filtragem de empresa para trabalho, metadados globais identificados como workspace; cookies da sessão humana original seguem somente para rotas fixas loopback, que reaplicam ACL nativa. Sem conta de serviço substituta.
- Edições de trabalho/automação existente: campos explicitamente permitidos em projetos, metas, tickets, heartbeats, rotinas e gatilhos. Rotinas solicitam recarga do scheduler. Não há URL livre, shell ou remoção genérica. O adapter administrativo pode selecionar/configurar provider e habilitar/instalar plugin pedido pelo usuário, pelas APIs existentes. Instalação mantém scan e validações nativas; uma recusa não é contornada. Configuração de MCP permanece consultável, sem adapter de escrita. Nada disso é executado durante o rollout. Documentos de skill, memória do agente e materiais exigem hash da versão lida e backup antes da escrita. Uma skill editada continua sendo documento, sem execução implícita.
- Históricos continuam em seus bancos e registros. Ler histórico autorizado não depende de admitir nova sessão de agente inativo. Sessão assinada exige elegibilidade antes de voz/provider.

Documentação do protocolo de imagens: https://developers.openai.com/api/reference/resources/images/methods/generate

## Aprovações e YOLO Mode

A fonte única é a configuração existente `config/workspace.yaml:chat.trustMode`, lida pelo mesmo getter do Harness. Ligado dispensa aprovação do aplicativo para as ações disponibilizadas no Live; desligado gera cartão de conferência no chat. Handoff continua automático conforme autorizado. O toggle não é alterado no deploy e não pode ser ligado pelo modelo. Pedidos aguardando aprovação são cifrados com chave derivada do segredo já existente da aplicação, com prévia sem credenciais e claim de execução único. ACL, empresa, manifesto e validações são rechecados ao aplicar. Não dispensa permissões do ambiente nem cria capacidade ausente.

## Remoção física e preservação de rotinas

31 identificadores são retirados do catálogo. 30 definições nativas são movidas byte a byte para a biblioteca de papéis; o plugin Reach é capturado da instalação viva pela migração. O mapa de responsabilidade está em `scripts/squad-retirements.json`. A migração copia/verifica definições e memórias, mantém originais em backup com journal e transfere apenas tickets pendentes sem lock. Finalizados, bloqueados, conversas, logs, configurações e dados de mídia não são apagados.

Scheduler, heartbeat schema e ADW/provider CLI resolvem os identificadores históricos para playbooks, evitando `--agent` que aponta para arquivo retirado. O bootstrap executa a migração sob o lock existente. Telegram e media-worker não são atualizados. Uma futura reinicialização do Telegram antigo pode recopiá-los do seed antigo; o catálogo do dashboard ignora os identificadores aposentados e os bootstraps revisados voltam a migrá-los. Resolver definitivamente esse seed do Telegram exige revisão própria.

## Publicação e rollback

Push de release não dispara os gatilhos de CI/main. Não é necessário merge em main. O workflow existente `docker-publish-britto.yml` permite workflow_dispatch na branch. Dashboard usa target dashboard. O workflow não tem target runtime isolado: target core publica runtime e uma imagem adicional de dashboard da base do runtime; somente a imagem runtime será aplicada ao scheduler. Essa imagem adicional de dashboard não é aplicada.

Antes da produção: registrar SHA/digests, specs, env/config/mount hashes, backups consistentes dos bancos e arquivos de agentes/memórias, journal da migração e config ElevenLabs. Atualizar só scheduler e dashboard com digest imutável, sem reconstruir env/mounts. Aplicar contrato de ferramentas/prompt somente após o dashboard correspondente estar saudável. O script lê o estado remoto, impede concorrência, faz PATCH de folhas específicas e confere preservação de modelo/TTS/voz/platform/workflow.

Rollback: restaurar prompt/tool_ids da cópia restrita do agente, recolocar os dois digests anteriores com update apenas de imagem; restaurar definições retiradas do journal se for preciso voltar o scheduler antigo. Memórias importadas e novas saídas permanecem, sem limpar volumes. Reverter assignee somente para tickets que ainda tenham o novo responsável e estejam pendentes/sem lock; não restaurar o banco inteiro sobre transações recentes. Canary permanece desligado. Specs anteriores e backup completo da implantação anterior continuam preservados.

## Verificação

Pytest usa bancos temporários e mocks de provider/fila; Node usa o código real com transporte/áudio simulados. Browser QA usa somente identidade e estados locais, 375/812/1440, sem login em produção nem credenciais fabricadas. Foram inspecionadas capturas reais dos fixtures; isso não comprova qualidade de chamada real. Build e diff-check devem ser executados no HEAD exato antes do push. Evidências e resultados finais ficam no relatório de implantação.
