"""Fase 1D da esteira de vídeo: resumo temático — reúne, num único vídeo
16:9 contínuo, só os trechos de uma gravação longa relacionados a um tema
pedido (ex.: "Sistema Britto" e perguntas da audiência respondidas).
Pedido real do Felipe em 30/07/2026, pensando numa segunda versão comercial
menor que a call inteira de 3h+.

Mesma regra das Fases 1B/1C (modelo só onde há julgamento): escolher QUAIS
trechos pertencem ao tema é julgamento editorial (`propor_resumo_tematico`);
cortar e concatenar é execução determinística — reaproveita `cortar()` de
`media_audio.py` direto, sem reimplementar. `cortar()` já recebe trechos a
MANTER (não a remover), que é exatamente a semântica de que precisamos
aqui — nenhuma inversão necessária, diferente de `aplicar_corte_editorial`.

Sem limite de duração por trecho (diferente de `cortes_virais.py`): um
trecho sobre o tema pode durar 30s ou 8 minutos, dependendo de quanto a
pessoa falou sobre aquilo — limitar duração aqui cortaria no meio do
próprio assunto que se quer manter.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from media_audio import Progresso, Trecho, cortar
from provider_fallback import invoke_with_fallback
from transcricao import Palavra

PROMPT_RESUMO = """Você está selecionando, de uma live já editada, TODOS os trechos \
relacionados a um tema específico, pra montar um vídeo-resumo só sobre isso.

Tema: {tema}

Escolha TODOS os trechos (podem ser vários, de qualquer duração) em que a conversa \
trata diretamente desse tema — não é preciso que cada trecho funcione sozinho fora de \
contexto (isso vai virar um resumo contínuo, não clipes soltos), mas cada trecho deve \
ter início e fim que fazem sentido tirados do resto — não corte no meio de uma frase \
nem no meio de um raciocínio.

NÃO inclua: menções de passagem ao tema (uma frase citando o nome sem desenvolver), \
nem trechos que só fazem sentido junto de um assunto diferente do tema pedido.

Transcrição (timestamps em segundos, [inicio-fim] texto):

{transcricao}

Responda SÓ com um array JSON, sem texto antes ou depois, no formato:
[{{"inicio": 123.4, "fim": 356.7, "assunto": "o que especificamente é tratado aqui"}}]

Se nada no material trata do tema pedido, responda [].
"""


def _agrupar_em_linhas(palavras: list[Palavra], *, janela_s: float = 6.0) -> list[tuple[float, float, str]]:
    if not palavras:
        return []
    linhas: list[tuple[float, float, str]] = []
    inicio_linha = palavras[0].inicio
    buffer: list[str] = []
    for p in palavras:
        if p.inicio - inicio_linha > janela_s and buffer:
            linhas.append((inicio_linha, palavras[palavras.index(p) - 1].fim, " ".join(buffer)))
            inicio_linha = p.inicio
            buffer = []
        buffer.append(p.texto)
    if buffer:
        linhas.append((inicio_linha, palavras[-1].fim, " ".join(buffer)))
    return linhas


def formatar_para_selecao(palavras: list[Palavra]) -> str:
    linhas = _agrupar_em_linhas(palavras)
    return "\n".join(f"[{i:.0f}-{f:.0f}] {t}" for i, f, t in linhas)


def _extrair_json_array(bruto: str) -> list[dict]:
    """Mesmo achado ao vivo de cortes_virais.py/corte_editorial.py
    (29/07/2026): o modelo às vezes devolve aspas simples (sintaxe Python)
    ou um nível extra de escape em vez de JSON estrito."""
    bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", bruto.strip())
    inicio = bruto.find("[")
    fim = bruto.rfind("]")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError(f"resposta do modelo sem array JSON reconhecível: {bruto[:200]!r}")
    trecho = bruto[inicio:fim + 1]
    try:
        return json.loads(trecho)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(trecho)
    except (ValueError, SyntaxError):
        pass
    try:
        desescapado = json.loads('"' + trecho + '"')
        return json.loads(desescapado)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"resposta do modelo não é JSON nem literal Python válido: {trecho[:200]!r}") from exc


def propor_resumo_tematico(palavras: list[Palavra], tema: str, *, cwd: Path,
                            timeout_seconds: int = 900) -> list[dict]:
    """Chama o modelo pra escolher todos os trechos sobre `tema`. Devolve
    lista de {inicio, fim, assunto}, validada (dentro do vídeo, sem
    sobreposição, ordenada por início) — nunca confia cegamente na resposta.

    `force_provider="opencode"` pelo mesmo motivo de sempre nesta esteira:
    Dockerfile.media-worker só instala esse binário (ver
    .claude/rules/esteira-de-video.md item 0).
    """
    prompt = PROMPT_RESUMO.format(tema=tema, transcricao=formatar_para_selecao(palavras))
    resultado = invoke_with_fallback(
        prompt=prompt, timeout_seconds=timeout_seconds, agent="", cwd=cwd,
        force_provider="opencode",
    )
    if resultado.get("status") != "success":
        raise RuntimeError(f"proposta de resumo temático falhou (status={resultado.get('status')}): {resultado.get('error')}")

    bruto = resultado.get("output") or ""
    itens = _extrair_json_array(bruto)

    duracao_total = palavras[-1].fim if palavras else 0.0
    trechos: list[dict] = []
    for item in itens:
        try:
            inicio, fim = float(item["inicio"]), float(item["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if fim <= inicio:
            continue
        inicio = max(0.0, inicio)
        fim = min(duracao_total, fim) if duracao_total else fim
        if fim <= inicio:
            continue
        trechos.append({"inicio": inicio, "fim": fim, "assunto": item.get("assunto", "")})

    trechos.sort(key=lambda t: t["inicio"])
    sem_sobreposicao: list[dict] = []
    fim_anterior = -1.0
    for t in trechos:
        if t["inicio"] < fim_anterior:
            continue
        sem_sobreposicao.append(t)
        fim_anterior = t["fim"]

    return sem_sobreposicao


def montar_resumo_tematico(video: Path, trechos_aprovados: list[dict], saida: Path, *,
                            progresso: Progresso | None = None) -> dict:
    """Corta e concatena os trechos já aprovados num único vídeo contínuo —
    execução determinística, reaproveitando `cortar()` de media_audio.py
    (mesma função que a Fase 1B usa pra aplicar corte editorial). Nunca
    decide o que entra: quem decidiu foi o gate humano, isto só executa.
    """
    manter = [Trecho(float(t["inicio"]), float(t["fim"])) for t in trechos_aprovados]
    cortar(video, manter, saida, progresso=progresso)
    duracao_final_s = sum(t.duracao for t in manter)
    return {
        "duracao_final_s": round(duracao_final_s, 2),
        "trechos_incluidos": len(manter),
    }
