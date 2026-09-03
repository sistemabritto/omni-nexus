# Tema do blog.sistemabritto.com.br

Tema Ghost feito para o blog do Sistema Britto. Dark premium, sem framework,
sem requisição a terceiros.

## O que ele é

- **Um arquivo de CSS** (~32 KB) e **um de JS** (~5 KB, não minificado).
- **Fonte self-hosted** (Geist), sem Google Fonts — nenhuma requisição sai
  para fora do domínio.
- Todo efeito visual é CSS: aurora animada, malha de fundo, holofote no
  cartão, marquee, glass na navegação, reveal no scroll.
- O JavaScript só faz o que CSS não faz: menu, sentinela de scroll da
  navegação, contador de números e a posição do cursor no cartão. Tudo com
  `IntersectionObserver`, nada em loop de scroll.

## Decisões que não são óbvias

- **O reveal só esconde o conteúdo se o script confirmar que vai revelá-lo.**
  A classe `js-revela` entra no `<html>` pelo JS; sem ele, tudo nasce visível.
  É a falha mais cara desse padrão: script quebrado deixando a página em
  branco.
- **`font-display: swap`** e preload só da fonte de texto. A monoespaçada
  aparece em código e selo, raramente na primeira dobra — precarregá-la
  disputaria banda com o LCP.
- **O primeiro cartão da home é `eager` + `fetchpriority="high"`**; os demais
  são `lazy`. Ele é o LCP da página.
- **`prefers-reduced-motion` desliga tudo**, inclusive o contador, que passa a
  mostrar o valor final direto.

## Desenvolvimento

```bash
npx gscan .          # valida contra as regras do Ghost
zip -r tema.zip . -x '.git/*' '*.zip'
```

O push na `main` publica sozinho (ver `.github/workflows/deploy-theme.yml`).
Exige os secrets `GHOST_ADMIN_API_URL` e `GHOST_ADMIN_API_KEY`.

## Rollback

O Ghost mantém os temas instalados. Para voltar ao anterior, ative o Casper em
**Settings → Design**, ou pela Admin API:

```
PUT /ghost/api/admin/themes/casper/activate/
```

Backup do tema e do banco antes da primeira troca:
`/root/backups/ghost/` na VPS.
