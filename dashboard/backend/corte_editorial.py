"""Fase 1B da esteira de vídeo: corte editorial proposto pelo modelo, aprovado
em lote pelo humano — nunca cortado sem gate (mesma regra da esteira de
conteúdo, ver `.claude/rules/esteira-de-conteudo.md`).

Marcar o que cortar é julgamento (regra do workspace: modelo só onde há
decisão editorial). O que é Python puro (transcrever, montar a página,
somar minutos) fica em `transcricao.py` e nas funções determinísticas daqui.
"""

from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path

from provider_fallback import invoke_with_fallback
from transcricao import Segmento

PROMPT_CORTE = """Você está editando a transcrição de uma live já cortada (silêncios já \
removidos). A tarefa é marcar trechos ADICIONAIS que deveriam ser cortados do vídeo \
final — não os que ficam.

O que procurar: tangentes longas sem valor pro tema, repetições do mesmo ponto, \
problemas técnicos mencionados na fala (queda de conexão, "deixa eu recomeçar essa \
parte", pausas para resolver algo fora do assunto), ou blocos que claramente não \
agregam a quem for assistir depois.

ABERTURA: se os primeiros minutos forem só uma pessoa falando sozinha esperando \
os outros participantes chegarem ou testando áudio/câmera (sem ainda apresentar o \
tema, sem gancho, sem ninguém reagindo), isso é candidato a corte mesmo sendo o \
INÍCIO do vídeo — não existe exceção "não corto o começo". Ache o primeiro momento \
em que o conteúdo de fato começa (apresentação do tema, entrada de outro \
participante, ou primeira ideia desenvolvida) e marque tudo antes disso, DESDE \
QUE não seja só alguém organizando o pensamento por poucos segundos — um minuto de \
preâmbulo é normal, cinco minutos de monólogo de espera não é.

O que NÃO marcar: conteúdo só porque é longo, opiniões, humor, ou qualquer trecho em \
que você não tenha certeza — na dúvida, não corta. Cortar demais é pior que cortar de menos.

Transcrição (timestamps em segundos, [inicio-fim]):

{transcricao}

Responda SÓ com um array JSON, sem texto antes ou depois, no formato:
[{{"inicio": 123.4, "fim": 145.0, "motivo": "explicação curta de por que cortar este trecho"}}]

Se nenhum trecho merece corte, responda [].
"""


def formatar_transcricao(segmentos: list[Segmento]) -> str:
    return "\n".join(f"[{s.inicio:.0f}-{s.fim:.0f}] {s.texto}" for s in segmentos)


def _extrair_json_array(bruto: str) -> list[dict]:
    """Extrai o array de cortes da resposta do modelo. Mesmo achado de
    `cortes_virais.py::_extrair_json_array` (29/07/2026): o modelo às vezes
    devolve sintaxe de dict Python (aspas simples) em vez de JSON estrito.
    `ast.literal_eval` aceita as duas sintaxes sem executar código arbitrário.
    """
    bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto.strip())
    inicio = bruto.find("[")
    fim = bruto.rfind("]")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError(f"resposta do modelo sem array JSON reconhecível: {bruto[:200]!r}")
    trecho = bruto[inicio:fim + 1]
    try:
        return json.loads(trecho)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(trecho)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"resposta do modelo não é JSON nem literal Python válido: {trecho[:200]!r}") from exc


def propor_cortes(segmentos: list[Segmento], *, cwd: Path, timeout_seconds: int = 600) -> list[dict]:
    """Chama o modelo (via provider_fallback, mesmo mecanismo do resto da
    esteira de vídeo) para marcar trechos a cortar. Devolve lista de
    {inicio, fim, motivo}, validada e ordenada — nunca confia cegamente no
    que o modelo devolveu.

    `force_provider="opencode"` é obrigatório aqui: Dockerfile.media-worker só
    instala o binário `opencode` (ver comentário no Dockerfile) — não instala
    `openclaude` nem `claude`. Sem o pin, `invoke_with_fallback` segue a cadeia
    de `config/providers.json` (que na VPS tem `active_provider=omnirouter`,
    cli_command `openclaude`), e todo attempt falha com "binary not found in
    PATH" até esgotar a cadeia em `anthropic:claude` — confirmado ao vivo em
    29/07/2026 num job real de 3h02 que queimou 3 transcrições Groq inteiras
    (19 blocos cada) reprocessando o mesmo erro a cada auto-retry antes de
    achar a causa. Este bug afeta `propor_cortes_virais` (cortes_virais.py)
    igualmente, mesmo mecanismo.
    """
    prompt = PROMPT_CORTE.format(transcricao=formatar_transcricao(segmentos))
    resultado = invoke_with_fallback(
        prompt=prompt, timeout_seconds=timeout_seconds, agent="", cwd=cwd,
        force_provider="opencode",
    )
    if resultado.get("status") != "success":
        raise RuntimeError(f"proposta de corte falhou (status={resultado.get('status')}): {resultado.get('error')}")

    bruto = resultado.get("output") or ""
    itens = _extrair_json_array(bruto)

    duracao_total = segmentos[-1].fim if segmentos else 0.0
    cortes: list[dict] = []
    for item in itens:
        try:
            inicio, fim = float(item["inicio"]), float(item["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if fim <= inicio or inicio < 0 or fim > duracao_total + 1:
            continue
        cortes.append({"inicio": inicio, "fim": fim, "motivo": str(item.get("motivo") or "").strip()})

    return sorted(cortes, key=lambda c: c["inicio"])


def _fmt_tempo(s: float) -> str:
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def gerar_pagina_revisao(*, titulo: str, cortes: list[dict], duracao_original_s: float) -> str:
    """HTML autossuficiente (sem CDN, sem fonte externa — regra de artifacts.md)
    listando os cortes propostos, pra publicar via /api/shares.
    """
    total_cortado = sum(c["fim"] - c["inicio"] for c in cortes)
    linhas = "\n".join(
        f'<tr><td>{i + 1}</td><td>{_fmt_tempo(c["inicio"])} – {_fmt_tempo(c["fim"])}</td>'
        f'<td>{_fmt_tempo(c["fim"] - c["inicio"])}</td><td>{html.escape(c["motivo"])}</td></tr>'
        for i, c in enumerate(cortes)
    )
    if not cortes:
        linhas = '<tr><td colspan="4" class="vazio">Nenhum corte proposto — a transcrição não teve trecho que se qualificasse.</td></tr>'

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corte editorial — {html.escape(titulo)}</title>
<style>
:root {{ --bg:#0a0a0a; --fg:#eee; --muted:#999; --linha:#1c1c1c; --acento:#22c55e; }}
@media (prefers-color-scheme: light) {{
  :root {{ --bg:#fafafa; --fg:#111; --muted:#666; --linha:#e5e5e5; --acento:#16a34a; }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
        font-family:-apple-system,Segoe UI,Inter,sans-serif; }}
.wrap {{ max-width:920px; margin:0 auto; }}
h1 {{ font-size:1.4rem; margin-bottom:.25rem }}
.sub {{ color:var(--muted); margin-bottom:1.5rem; font-size:.9rem }}
.resumo {{ display:flex; gap:1.5rem; flex-wrap:wrap; margin-bottom:1.5rem }}
.resumo div {{ background:var(--linha); border-radius:.6rem; padding:.75rem 1rem; }}
.resumo strong {{ display:block; font-size:1.3rem; color:var(--acento) }}
.resumo span {{ font-size:.8rem; color:var(--muted) }}
.tabela-wrap {{ overflow-x:auto; border:1px solid var(--linha); border-radius:.6rem }}
table {{ width:100%; border-collapse:collapse; font-size:.9rem }}
th, td {{ padding:.6rem .8rem; text-align:left; border-bottom:1px solid var(--linha) }}
th {{ color:var(--muted); font-weight:600; font-size:.8rem; text-transform:uppercase }}
td:nth-child(2), td:nth-child(3) {{ font-variant-numeric:tabular-nums; white-space:nowrap }}
.vazio {{ text-align:center; color:var(--muted); padding:2rem }}
</style></head>
<body><div class="wrap">
<h1>Corte editorial proposto</h1>
<p class="sub">{html.escape(titulo)} · duração atual {_fmt_tempo(duracao_original_s)}</p>
<div class="resumo">
<div><strong>{len(cortes)}</strong><span>trechos propostos</span></div>
<div><strong>{_fmt_tempo(total_cortado)}</strong><span>tempo a cortar</span></div>
<div><strong>{_fmt_tempo(duracao_original_s - total_cortado)}</strong><span>duração final estimada</span></div>
</div>
<div class="tabela-wrap"><table>
<thead><tr><th>#</th><th>Intervalo</th><th>Duração</th><th>Motivo</th></tr></thead>
<tbody>{linhas}</tbody>
</table></div>
</div></body></html>
"""
