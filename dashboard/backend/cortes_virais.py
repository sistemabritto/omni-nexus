"""Fase 1C da esteira de vídeo: cortes verticais curtos, prontos pra postar.

Duas responsabilidades separadas, mesma regra da 1B (modelo só onde há
julgamento — regra do workspace):

- Escolher QUAIS trechos valem virar corte é julgamento editorial: pede
  modelo (`propor_cortes_virais`).
- Recortar, enquadrar em 9:16, dar zoom e legendar é execução determinística:
  ffmpeg puro (`renderizar_corte_viral`), sem chamada de modelo.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from media_audio import FalhaDeMidia, Progresso
from provider_fallback import invoke_with_fallback
from transcricao import Palavra


def _rodar(cmd: list[str], *, o_que: str, timeout: int = 1800) -> str:
    """Mesmo padrão de `media_audio._rodar` — cada módulo determinístico da
    esteira mantém a própria cópia em vez de importar função de outro
    módulo com underscore (convenção de "privado", não pra atravessar
    módulo)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise FalhaDeMidia(f"{o_que}: estourou {timeout}s") from exc
    if r.returncode != 0:
        cauda = (r.stderr or "").strip().splitlines()[-6:]
        raise FalhaDeMidia(f"{o_que} falhou ({r.returncode}): " + " | ".join(cauda))
    return r.stderr or ""

PROMPT_VIRAL = """Você está escolhendo trechos de uma live já editada para virar cortes \
curtos verticais (Reels/Shorts/TikTok) — o formato que mais gera alcance e engajamento hoje.

Escolha até {max_cortes} trechos que funcionam SOZINHOS, sem o contexto do resto da live: \
uma ideia completa, uma afirmação forte, uma virada, uma explicação que resolve algo \
sozinha, um momento de humor ou tensão. Cada corte precisa ter início e fim que fazem \
sentido tirados do resto — não corte no meio de uma frase nem no meio de um raciocínio.

Duração de cada corte: entre 20 e 90 segundos. Prefira o mais curto que ainda entrega a \
ideia inteira — corte curto e direto viraliza mais que corte longo e completo.

NÃO escolha: trechos que dependem de algo dito antes pra fazer sentido, conversa de \
transição, agradecimentos, ou qualquer trecho em que você não tenha certeza que funciona \
sozinho.

Transcrição (timestamps em segundos, [inicio-fim] texto):

{transcricao}

Responda SÓ com um array JSON, sem texto antes ou depois, no formato:
[{{"inicio": 123.4, "fim": 178.9, "titulo": "gancho curto pro post, até 60 caracteres", \
"motivo": "por que esse trecho funciona sozinho"}}]

Se nenhum trecho do material funciona como corte independente, responda [].
"""


def _agrupar_em_linhas(palavras: list[Palavra], *, janela_s: float = 6.0) -> list[tuple[float, float, str]]:
    """Agrupa palavra por palavra em linhas de ~`janela_s` segundos — dá ao
    modelo granularidade fina sem estourar o prompt com uma linha por palavra."""
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
    return "\n".join(f"[{ini:.0f}-{fim:.0f}] {texto}" for ini, fim, texto in linhas)


def _extrair_json_array(bruto: str) -> list[dict]:
    """Extrai o array de cortes da resposta do modelo. Achado ao vivo em
    29/07/2026: o modelo às vezes devolve sintaxe de dict Python (aspas
    simples) em vez de JSON estrito — `json.loads` rejeita com "Expecting
    property name enclosed in double quotes". `ast.literal_eval` aceita as
    duas sintaxes (JSON válido é um subconjunto de literais Python) sem
    executar código arbitrário — é avaliação de literal, não `eval`.
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


DURACAO_MIN_S = 20.0
DURACAO_MAX_S = 90.0


def propor_cortes_virais(palavras: list[Palavra], *, cwd: Path, max_cortes: int = 6,
                         timeout_seconds: int = 600) -> list[dict]:
    """Chama o modelo pra escolher trechos que funcionam como corte curto
    independente. Devolve lista de {inicio, fim, titulo, motivo}, validada
    (duração dentro da faixa, dentro do vídeo, sem sobreposição) — nunca
    confia cegamente no que o modelo devolveu.

    `force_provider="opencode"` é obrigatório: ver o mesmo comentário em
    `corte_editorial.py::propor_cortes` — Dockerfile.media-worker só instala
    o binário `opencode`, e sem o pin a chamada segue a cadeia global de
    `config/providers.json` (openclaude/claude), que não existe neste
    container e falha sempre. Achado ao vivo em 29/07/2026 no primeiro job
    real desta função, depois de 3 auto-retries reprocessando as mesmas 19
    transcrições Groq (job 69cb16f5, marcado `failed` manualmente pra parar
    o loop antes deste fix).
    """
    prompt = PROMPT_VIRAL.format(max_cortes=max_cortes, transcricao=formatar_para_selecao(palavras))
    resultado = invoke_with_fallback(
        prompt=prompt, timeout_seconds=timeout_seconds, agent="", cwd=cwd,
        force_provider="opencode",
    )
    if resultado.get("status") != "success":
        raise RuntimeError(f"proposta de corte viral falhou (status={resultado.get('status')}): {resultado.get('error')}")

    itens = _extrair_json_array(resultado.get("output") or "")
    duracao_total = palavras[-1].fim if palavras else 0.0

    cortes: list[dict] = []
    for item in itens:
        try:
            inicio, fim = float(item["inicio"]), float(item["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        duracao = fim - inicio
        if duracao < DURACAO_MIN_S or duracao > DURACAO_MAX_S:
            continue
        if inicio < 0 or fim > duracao_total + 1:
            continue
        cortes.append({
            "inicio": inicio, "fim": fim,
            "titulo": str(item.get("titulo") or "").strip()[:80],
            "motivo": str(item.get("motivo") or "").strip(),
        })

    cortes.sort(key=lambda c: c["inicio"])
    # Overlap é sinal de o modelo ter escolhido o mesmo momento duas vezes com
    # bordas diferentes — fica só o primeiro, que veio mais bem formado
    # (ordem de resposta costuma refletir confiança).
    sem_sobreposicao: list[dict] = []
    fim_anterior = -1.0
    for c in cortes:
        if c["inicio"] < fim_anterior:
            continue
        sem_sobreposicao.append(c)
        fim_anterior = c["fim"]

    return sem_sobreposicao[:max_cortes]


# ── Renderização (determinística, sem modelo) ──────────────────────────────

LARGURA_SAIDA = 1080
ALTURA_SAIDA = 1920

# Zoom lento e contínuo — "dá zoom" no pedido do Felipe, sem ser agressivo a
# ponto de cansar em 20-90s de corte. 1.0 -> 1.12 ao longo do trecho inteiro.
ZOOM_FINAL = 1.12


@dataclass
class LinhaLegenda:
    inicio: float
    fim: float
    palavras: list[Palavra]


def _agrupar_legenda(palavras_trecho: list[Palavra], *, max_palavras: int = 4) -> list[LinhaLegenda]:
    """Legenda em blocos curtos (até 4 palavras por vez) é o padrão de corte
    viral atual — bloco de frase inteira na tela é ilegível em celular."""
    linhas: list[LinhaLegenda] = []
    for i in range(0, len(palavras_trecho), max_palavras):
        bloco = palavras_trecho[i:i + max_palavras]
        if bloco:
            linhas.append(LinhaLegenda(inicio=bloco[0].inicio, fim=bloco[-1].fim, palavras=bloco))
    return linhas


def _ass_timestamp(s: float) -> str:
    cs = round(s * 100)
    h, resto = divmod(cs, 360000)
    m, resto = divmod(resto, 6000)
    seg, cent = divmod(resto, 100)
    return f"{h}:{m:02d}:{seg:02d}.{cent:02d}"


def _escapar_ass(texto: str) -> str:
    return texto.replace("\\", "").replace("{", "").replace("}", "")


def montar_legenda_ass(palavras_trecho: list[Palavra], *, offset: float, destino: Path) -> Path:
    """Gera legenda .ass com destaque palavra-a-palavra (estilo karaokê via
    tag \\k do ASS) — é a técnica de legenda que domina corte curto hoje,
    bem diferente de legenda de frase inteira parada na tela.

    Filtra palavra que termina antes do `offset` ANTES de agrupar em linhas —
    não depois. `_agrupar_legenda` junta por contagem (até 4 palavras), não
    por tempo, então uma palavra de fora do trecho podia cair no mesmo bloco
    de uma palavra válida e vazar pra legenda mesmo com a linha inteira tendo
    `fim` positivo. A função precisa ser correta sozinha, não confiar que
    quem chama já filtrou (o pipeline real filtra em `renderizar_corte_viral`,
    mas isso é reforço, não a garantia).
    """
    palavras_trecho = [p for p in palavras_trecho if p.fim > offset]
    cabecalho = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA_SAIDA}
PlayResY: {ALTURA_SAIDA}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,84,&H00FFFFFF,&H0000D4FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas_evento = []
    for linha in _agrupar_legenda(palavras_trecho):
        inicio_local = linha.inicio - offset
        fim_local = linha.fim - offset
        if fim_local <= 0:
            continue
        inicio_local = max(0.0, inicio_local)

        # \k em centésimos de segundo, um por palavra — o player acende cada
        # palavra na hora certa em vez de mostrar a linha inteira estática.
        partes = []
        for p in linha.palavras:
            duracao_cs = max(1, round((p.fim - p.inicio) * 100))
            partes.append(f"{{\\k{duracao_cs}}}{_escapar_ass(p.texto)}")
        texto = " ".join(partes)

        linhas_evento.append(
            f"Dialogue: 0,{_ass_timestamp(inicio_local)},{_ass_timestamp(fim_local)},"
            f"Default,,0,0,0,,{texto}"
        )

    destino.write_text(cabecalho + "\n".join(linhas_evento) + "\n", encoding="utf-8")
    return destino


def renderizar_corte_viral(video: Path, corte: dict, palavras_todas: list[Palavra],
                           saida: Path, *, trabalho: Path,
                           progresso: Progresso | None = None) -> dict:
    """Recorta o trecho, enquadra em 9:16 (crop centralizado — sem detecção
    de rosto, ver limitação no docstring do módulo), aplica zoom lento e
    queima a legenda palavra-a-palavra.

    Crop centralizado é a limitação real desta V1: se o assunto principal do
    quadro (rosto, tela compartilhada) não estiver no centro do frame 16:9
    original, o corte vertical pode cortá-lo fora. Rastrear o assunto
    exigiria detecção de rosto/objeto, fora do escopo desta primeira versão.
    """
    inicio, fim = corte["inicio"], corte["fim"]
    duracao = fim - inicio
    trabalho.mkdir(parents=True, exist_ok=True)

    palavras_trecho = [p for p in palavras_todas if p.fim > inicio and p.inicio < fim]
    ass = montar_legenda_ass(palavras_trecho, offset=inicio, destino=trabalho / "legenda.ass")

    if progresso:
        progresso("corte viral", f"renderizando {duracao:.0f}s — {corte.get('titulo', '')[:40]}")

    # zoompan reinicia o zoom por chamada; `d` = frames por frame de saída (1
    # = 1:1, sem slow-motion), `fps` precisa bater com o de saída pra 'on'
    # (número do frame) render o zoom no ritmo certo pro `duracao` do trecho.
    fps = 24
    total_frames = max(1, round(duracao * fps))
    filtro = (
        f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
        f"scale={LARGURA_SAIDA}:{ALTURA_SAIDA},"
        f"zoompan=z='min(1+({ZOOM_FINAL}-1)*on/{total_frames},{ZOOM_FINAL})'"
        f":d=1:s={LARGURA_SAIDA}x{ALTURA_SAIDA}:fps={fps},"
        f"subtitles={_escapar_caminho_ffmpeg(ass)}"
    )

    _rodar(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio:.3f}", "-t", f"{duracao:.3f}",
         "-i", str(video), "-vf", filtro,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", str(saida)],
        o_que="renderização do corte viral", timeout=1800,
    )

    if not saida.is_file():
        raise FalhaDeMidia(f"corte viral não gerou {saida}")

    return {
        "inicio": inicio, "fim": fim, "duracao_s": round(duracao, 1),
        "titulo": corte.get("titulo", ""), "motivo": corte.get("motivo", ""),
        "largura": LARGURA_SAIDA, "altura": ALTURA_SAIDA,
    }


def _escapar_caminho_ffmpeg(caminho: Path) -> str:
    """O filtro `subtitles=` do ffmpeg trata ':' como separador de opção —
    caminho absoluto no Linux ('/workspace/...') não tem ':', mas se algum dia
    rodar em ambiente com drive letter isso quebra silenciosamente."""
    return str(caminho).replace("\\", "/").replace(":", "\\:")
