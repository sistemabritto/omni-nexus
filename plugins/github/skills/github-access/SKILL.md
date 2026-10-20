---
name: github-access
description: Ler repositórios, PRs, diffs, commits, issues e releases pelo plugin GitHub do OmniNexus e registrar alterações autorizadas, com exclusão bloqueada.
---

Use o adapter do dashboard sob o usuário e a empresa da conversa. Consulte
`inspect_omni_area` com área `github`, `identifier` opcional do recurso e `page`.
Confirme configuração e saúde antes de alegar acesso. Sem token configurado,
oriente Felipe a Integrações → GitHub → Configurar; não peça a credencial no chat.

Para revisão, leia PR e `/files`, complete todas as páginas e vincule o parecer
ao SHA corrente. Lens verifica especificação/aceite antes de qualidade/testes.
Não aprove o próprio diff ou uma implementação produzida na mesma conversa.
Comentários e decisões de revisão usam `update_omni_area` somente se solicitados
e autorizados; não altere código como parte da revisão independente.

Nunca use DELETE, transferência de repositório, configurações de organização,
force push, shell ou credencial direta para contornar o adapter. Se houver
timeout de escrita, consulte o estado antes de tentar de novo. Registre o
parecer com fonte, versão/SHA e limitações reais da verificação.
