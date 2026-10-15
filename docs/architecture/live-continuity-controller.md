# Controlador Live e continuidade

Integração frontend com o contrato `feat/live-continuity-endpoints` (`8823faa`).
Requer integrar esse backend e habilitar sua flag explicitamente; este PR não
altera backend, configuração de produção, modelo, voz remota ou dispatcher.

| Caminho | Implementado | Evidência | Produção |
| --- | --- | --- | --- |
| Conectar → vínculo autenticado → continuity → events → read → contextual_update | Sim | Controlador TS real, HTTP/provedor simulados | Pendente |
| Texto digitado → transcript ACK → user_message | Sim | Teste do controlador | Pendente |
| Eventos finais de voz/assistente → transcript | Sim | Teste do controlador; sem áudio real | Pendente |
| Retry de gravação com ID/payload original | Sim | Falha simulada e retry | Pendente |
| Reconexão → mesma conversa lógica → eventos paginados | Sim | Teste do controlador | Pendente |
| Revisões/retrações recebidas → upsert/remove | Sim | Teste do controlador | Pendente |
| Buscar tickets/comentários autorizados | Sim | Painel e gateway; fixture visual | Pendente |
| Dispatcher → recordWork → work-events → events | Hook público disponível | Sem executor real neste PR | Pendente |
| Hermes / Codex / Cursor como harness | Não implementado aqui | Nenhuma integração provada | Pendente |

`ManagedSession.recordWork(type,id)` é um hook para o dispatcher existente depois
de criar/atualizar um registro real. Não recebe texto/URL do modelo. Não há chamada
automática desse hook porque o client tool atual somente lê contexto; não existe
resultado de execução para conectar sem inventar um dispatcher paralelo.

Gravações pendentes ficam no singleton durante navegação SPA e término da voz.
Não são colocadas em localStorage. Logout/desmontagem da área autenticada sempre
encerra áudio/socket e limpa dados/fila da identidade anterior, mesmo com ACK pendente. A tela bloqueia nova conexão/conversa enquanto
há erro ou ACK pendente e oferece retry. Fechar o navegador antes do ACK ainda pode
perder a fila local; o aviso de saída não substitui armazenamento durável.

IDs de transcrição são criados uma vez por evento final recebido e conservados
durante retries HTTP. Não deduplicam um replay do mesmo evento feito pelo provedor
sem identidade estável, nem registram `agent_response_correction`; esses caminhos
precisam de contrato de identidade/revisão do SDK e teste adicional.

Contexto enviado ao provedor e resultados do client tool têm limite de 24.000
caracteres serializados, com falha explícita acima disso. É limite de transporte,
não contador exato de tokens. Dados recuperados são marcados como referência não
confiável; não são instruções. Não há treinamento ou confirmação automática de notas.

Polling `/events` usa cursor a cada cinco segundos somente durante conexão ativa.
Quando existem eventos de trabalho em cache, a próxima atualização repagina desde
zero para revalidar também registros sem nova revisão; isso custa mais leituras em
conversas extensas. O backend revalida os registros retornados. Não se pode
prometer retirar do provedor texto já transmitido: correções/revogação exigem
fechar a conexão e reidratar uma nova. Não habilitar rollout amplo antes dessa revisão.

Antes de produção, testar recuperação de um trabalho real autorizado, reconexão,
contexto entregue ao provedor real e retorno do dispatcher com evidência. Testes
simulados deste PR não demonstram execução de tarefa nem qualidade da resposta LLM.
