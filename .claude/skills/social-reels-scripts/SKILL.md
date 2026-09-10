---
name: social-reels-scripts
description: "Gera roteiro completo de Reels/vídeo curto — não só o gancho. Combina o banco de 200 ganchos (social-hook-bank) com 14 estruturas de roteiro (PASA, AIDA, AIU, ISAC, CRESA, COBA, UUUU, OMDEPCRT, PIBOF, OPCSOA, ODSOU, NPPC, AAA, DDC), um quadro de conectores/transições, e uma matriz de temas específica do Sistema Britto (dores, avatares, ângulos, objeções do funil /sistema). Use quando o usuário pedir 'roteiro de reels', 'roteiro de vídeo', 'estrutura pro vídeo', 'me ajuda a montar o vídeo inteiro' (não só o gancho), ou pedir tema/pauta de conteúdo pro Instagram do Sistema Britto."
metadata:
  version: 1.0.0
---

# Gerador de Roteiro de Reels

Para coprodução com Magneto, campanha OpenReply ou planejamento dos 120–150
Reels, leia primeiro `references/coproducao-magneto.md`. Esse contrato atualiza
o formato abaixo e os CTAs históricos da matriz para o pedido de 10/09/2026.

## Pipeline (nessa ordem)

1. **Tema.** Se não vier pronto, puxe de `references/matriz-temas-sistemabritto.md`
   — escolha a célula certa pelo pilar (RASTREAR/VIBE CODAR/MONETIZAR) e pelo
   avatar do público daquele vídeo.
2. **Gancho.** Puxe de `social-hook-bank` (200 ganchos + 25 visuais) — escolha
   pelo mecanismo psicológico certo pro tema (tabela de blocos no SKILL.md
   daquela skill). Adapte, nunca copie literalmente.
3. **Estrutura do corpo.** Escolha uma das 14 em `references/estruturas-de-linguagem.md`
   pela tabela "Como escolher" — ela decide os beats entre o gancho e o CTA.
4. **Transições.** Ao escrever os beats, puxe frases de
   `references/quadro-conectores.md` em vez de inventar conector genérico
   toda vez ("bom galera", "então é isso") — mantém o roteiro fluido sem soar
   repetitivo entre vídeos.
5. **CTA + funil.** Todo roteiro fecha apontando pro funil certo
   (`/sistema`, `/vps`, `/whatsapp`, `/socialjobs`, `/zapclub` — mesma lógica
   de `funil_de()` em `escritor_de_artigo.py`), nunca genérico.

## Regra de ouro (vale pras 3 referências)

Nenhum número, caso ou depoimento inventado — só os 4 casos reais fechados
(Laboratório de Insights, JURISMART, Voice Dream, Omni Nexus), e só quando
fizer sentido pro tema. Campo de garantia/urgência sem confirmação real fica
em aberto, nunca preenchido com algo fabricado (ver regra de uso em
`matriz-temas-sistemabritto.md`).

## Formato de saída de um roteiro

```
Gancho: <frase adaptada, referenciando o bloco de origem>
Estrutura: <sigla da estrutura de linguagem escolhida>
Beats:
  1. <beat 1, com transição de quadro-conectores.md onde fizer sentido>
  2. <beat 2>
  3. <beat 3...>
CTA: <fala final>
Funil: <url + descrição>
```

## Fontes

- `references/estruturas-de-linguagem.md` — 14 estruturas de roteiro
- `references/quadro-conectores.md` — banco de frases de transição
- `references/matriz-temas-sistemabritto.md` — matriz de temas (dores,
  avatares, ângulos, objeções) específica do sistemabritto.com.br

## Relacionado

- `social-hook-bank` — banco de ganchos (usado no passo 2)
- `social-post-writer`, `linkedin-post-writer` (plugin) — mesma lógica de
  estrutura serve pra post de texto, não só vídeo
