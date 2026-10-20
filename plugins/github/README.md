# GitHub para os agentes

No OmniNexus, abra **Integrações → GitHub → Configurar**. Cole sua credencial no
campo protegido, salve e use **Testar conexão**. O formulário é o existente de
plugins: grava no `.env` persistente e recarrega o backend, sem copiar token para
chat, código, skill, resposta de ferramenta ou subprocesso do agente.

A integração testa a autenticação na API oficial. Depois, Lens deve listar os
repositórios e ler um PR para verificar também os escopos do token. Um teste
de autenticação bem-sucedido não comprova permissão para todos os repositórios.

O adapter em `dashboard/backend/live_github.py` aplica o vínculo explícito de
`config/live-github-access.json`: Felipe/Sistema Britto, todos os repositórios
de `sistemabritto`, com escrita autorizada. As demais empresas não herdam o
vínculo. DELETE, transferência, configurações administrativas e force push
ficam fora do adapter mesmo que o token tenha permissões mais amplas.

Leitura: `inspect_omni_area(area="github")`; para um PR,
`identifier="repos/sistemabritto/REPO/pulls/NUMERO"`; arquivos do diff usam o
sufixo `/files`. Continue com `page` enquanto `hasMore` for verdadeiro.

Escrita: `update_omni_area`, área `github`, identifier `sistemabritto/REPO`,
`changesJson={"method":"POST","path":"repos/sistemabritto/REPO/issues/NUMERO/comments","body":{"body":"Parecer"}}`.
Use apenas em resposta a um pedido autorizado. Revisões formais exigem Lens,
`commit_id` atual e independência do autor/contribuinte da conta autenticada.
O gate do app e a reserva de idempotência continuam ativos; não repetir
automaticamente uma escrita incerta.

Este plugin depende da versão do dashboard que inclui o adapter e os schemas
de ferramenta atualizados. Criar o plugin localmente não publica a versão nem
configura sua credencial. Nenhuma credencial é fornecida pelo pacote.
