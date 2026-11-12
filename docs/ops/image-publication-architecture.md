# Publicação de imagens OmniNexus

Um único workflow, docker-publish-britto.yml, publica no namespace fixo
docker.io/excarplex. O workflow legado docker-publish.yml foi retirado para
evitar publicação paralela em evoapicloud. OmniRoute permanece na sua stack
separada e não pertence à matriz deste fluxo.

## Consumidores

| Imagem | Serviços |
|---|---|
| evo-nexus-dashboard | dashboard |
| evo-nexus-runtime | scheduler e Telegram |
| evo-nexus-media-worker | worker de mídia |

Push em main e tags v*/rc* constroem as três imagens. Um disparo manual
oferece all, core, dashboard, media-worker ou media. Core inclui dashboard
e runtime; media inclui dashboard e worker. A opção media-worker permite
atualizar o worker sem reconstruir o dashboard. Os antigos booleanos de
seleção são substituídos por esse campo único.

O resolver rejeita eventos, refs e alvos fora do contrato. Todos os jobs
usam o mesmo SHA completo capturado no evento, com checkout explícito,
label OCI de revisão e resumo contendo o digest final de cada imagem.
Código consistente não significa dependências globais reproduzíveis: os
Dockerfiles ainda possuem instalações existentes de CLIs com latest.

Publicações compartilham um grupo global de concorrência e não cancelam
um build em execução. A fila usa queue: max, que aceita até 100 execuções
pendentes; além desse limite, novas execuções podem ser canceladas. A ordem
depende de quando cada execução entrou na espera, não garante ordem de commits.
A semântica foi conferida na documentação oficial do GitHub Actions:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
Builds antigos sem esse grupo não são drenados
retroativamente; concluir o ciclo em andamento antes de usar o novo fluxo.

Os secrets Docker Hub existentes servem somente ao login do registry.
Nenhuma configuração privada da VPS é buscada pelo workflow; o contexto
vem do checkout, com .env e .git excluídos pelo dockerignore. Nenhuma chave
de provider é fornecida por build-arg. Isso não substitui revisão de
segredos inadvertidamente versionados.

## Promoção e rollback

O build não efetua deploy. Depois de CI, inspeção OCI e smoke isolado,
promover os digests necessários, conferindo cada revisão e preservando
ENV, Args, mounts e dados atuais dos serviços. Registrar antes os digests,
verificar ociosidade e fazer backup consistente. Rollback usa os digests
anteriores e a configuração preservada; não restaura o banco automaticamente
sobre transações novas. Tags latest e aliases de branch não são referências
de rollback.

As verificações de contrato rodam em test_image_workflow_architecture.py.
Elas são offline e não publicam imagens. Alterar o workflow não comprova
um novo build/publicação; essa execução exige sua autorização própria.
