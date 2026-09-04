# Artefatos — onde entregar relatório, análise e documento visual

**Regra:** todo artefato entregável ao Felipe é publicado no **próprio Nexus**,
via `/api/shares`, e aparece em `https://nexus.workflowapi.com.br/shares`.
Nunca em artefato do Claude Code, nunca em serviço externo.

**Por quê:** o OmniNexus é o produto. Um relatório hospedado fora dele é um
relatório que o Felipe não controla, não versiona, não consegue mostrar a
cliente e some quando a sessão morre. Dentro do Nexus ele tem link estável,
lista em `/shares`, revogação, expiração opcional e fica no volume de workspace
junto do resto do trabalho.

## Como publicar

```python
from dashboard.backend.sdk_client import evo

# 1. o arquivo precisa existir DENTRO do workspace (é o que a API aceita)
caminho = "workspace/reports/[C]nome-do-relatorio-2026-07-25.html"

# 2. cria o share
share = evo.post("/api/shares", {
    "path": caminho,
    "expires_in": None,        # "1h" | "24h" | "7d" | "30d" | None (sem expirar)
})
print(share["url"])            # https://nexus.workflowapi.com.br/share/<token>
```

| Endpoint | Para quê |
|---|---|
| `POST /api/shares` | cria o link (exige `workspace:manage`) |
| `GET /api/shares` | lista os ativos |
| `GET /api/shares/by-path` | achar share existente de um arquivo — use antes de criar outro |
| `DELETE /api/shares/{token}` | revoga |
| `GET /api/shares/{token}/view` | serve o conteúdo (é o que o `/share/<token>` renderiza) |

**Antes de criar um share novo**, consulte `GET /api/shares/by-path` — republicar
o mesmo arquivo gera link novo e o antigo que você já mandou no Telegram vira
lixo. Atualize o arquivo no lugar e o link existente passa a servir a versão nova.

## Onde os arquivos moram

| Tipo | Pasta |
|---|---|
| Relatório de execução, status, pós-incidente | `workspace/reports/` |
| Análise de conteúdo, calendário, research | `workspace/social/` |
| Estratégia, plano, OKR | `workspace/strategy/` |
| Artefato de feature (PRD, verificação, retro) | `workspace/development/features/{slug}/` |

Prefixo `[C]` em tudo que o agente criou, como no resto do workspace.

## Como o HTML deve ser

O share serve o arquivo cru, então ele precisa se bastar:

- **Um arquivo só.** CSS inline no `<style>`, sem CDN, sem fonte externa —
  a página é servida com headers de segurança restritivos e requisição externa
  falha calada.
- **Tema claro e escuro.** Tokens CSS em `:root`, redefinidos em
  `@media (prefers-color-scheme: dark)`. O Felipe abre no celular e no desktop.
- **Rolagem lateral só onde precisa.** Tabela e bloco de código dentro de um
  container com `overflow-x: auto`; o `body` nunca rola de lado.
- **Sem lorem, sem número inventado.** Vale a mesma regra do briefing de marca:
  dado real com origem, ou nenhum dado.
- Fonte do sistema resolve. Monoespaçada é a escolha certa para identificador,
  hash, nome de serviço e variável de ambiente — é o vernáculo do assunto.

## CTA com rastreio de clique

O share serve o HTML com `Content-Security-Policy: default-src 'none'`
(defesa contra prompt injection lendo a sessão do superadmin) — **nenhum
JavaScript roda**, então `fetch()` de tracking embutido no artefato é
bloqueado de propósito, sem exceção.

Se o artefato tem CTA e o clique precisa ser medido, o botão vira um
`<a href>` puro apontando pra `/api/shares/<token>/click` em vez do destino
direto:

```html
<a href="https://nexus.workflowapi.com.br/api/shares/<TOKEN>/click?to=<URL-ENCODED>&label=<rotulo>"
   target="_blank" rel="noopener">Texto do CTA</a>
```

A rota registra o clique (`ShareEvent`) e devolve `302` pro destino real —
zero script, zero CSP pra afrouxar. `to` só aceita host num allowlist fixo em
`routes/shares.py::_CLICK_REDIRECT_ALLOWED_HOSTS`; domínio novo precisa ser
adicionado lá antes de funcionar. Use sempre a URL absoluta do share
(`https://nexus.workflowapi.com.br/...`), nunca relativa.

O resultado aparece em `/shares` no Nexus, coluna "Cliques (conversão)", ao
lado de "Visualizações" — não precisa consultar API na mão. Ver
`memory/rastreio-de-clique-em-artefato-share.md` para os dois erros que já
custaram um deploy quebrado cada (URL relativa, e o gate de autenticação
global de `app.py` tendo sua própria lista de caminhos públicos, separada do
decorator da rota).

## Quando NÃO usar share

- Conteúdo que vai para o blog → Ghost (`custom-int-ghost`).
- Conteúdo que vai para rede social → Postiz (`social-schedule-postiz`).
- Nota interna que ninguém vai abrir no navegador → markdown no workspace, sem
  share. Share é para o que se lê como página.

## Regras relacionadas

- `integrations.md` — Ghost, Postiz e o resto das integrações
- `dev-phases.md` — onde os artefatos de cada fase moram
