"""Cadeia de áudio da esteira de vídeo — o primeiro corte (Fase 1A).

Transforma uma gravação crua de live em algo publicável: ruído de sala fora,
volume no padrão das plataformas, silêncio removido. O que sai daqui alimenta o
corte editorial (1B) e os shorts (1C).

**A ordem não é negociável: denoise ANTES de detectar silêncio.** Medido em
28/07/2026 sobre uma live real de 3h28: depois do denoise,
`silencedetect=noise=-30dB:d=0.4` acha 17% do tempo como silêncio; no áudio cru
o piso de ruído fica acima do limiar e quase nada é detectado. Inverter a ordem
produz um job que roda inteiro, termina sem erro e não corta nada — o pior tipo
de defeito, porque parece sucesso.

Cada etapa é determinística e roda em ffmpeg ou no binário do DeepFilterNet.
Nenhuma chamada de modelo acontece aqui: cortar silêncio não é julgamento
(regra do workspace — modelo só onde há decisão editorial, que é a 1B).

Toda etapa longa aceita `progresso`, um callback que recebe (etapa, detalhe).
Sem isso, 1h46 de denoise é indistinguível de um job travado.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

Progresso = Callable[[str, str], None]

# Alvo de loudness. -14 LUFS é o que YouTube, Instagram e LinkedIn usam como
# referência de normalização; EBU R128 puro (-23) é padrão de broadcast e sai
# baixo demais na web. TP em -1.5 dá folga contra o clipping que o encoder da
# plataforma introduz ao recomprimir.
ALVO_LUFS = -14.0
ALVO_TP = -1.5
ALVO_LRA = 11.0

# O material de live chega com true peak em torno de 0 dBTP (medido: +0.03), e
# o DeepFilterNet acusa clipping o tempo todo quando recebe sinal saturado.
# Baixar 3 dB antes zera os avisos; o loudnorm devolve o nível depois.
PRE_GAIN_DB = -3.0

# Silêncio: mais baixo que -30 dB por pelo menos 0,4 s. Calibrado contra a
# gravação real — -35 e -40 dB cortam menos (14,5% e 13,4% contra 17,1%), e
# exigir 0,8 s de silêncio derruba o corte para 7,8%, deixando na peça as
# pausas que cansam quem assiste.
LIMIAR_SILENCIO_DB = -30
SILENCIO_MINIMO_S = 0.4

# Quanto de silêncio fica preservado em cada ponta do trecho falado. Sem isso o
# corte come o ataque da primeira sílaba e a peça soa picotada.
MARGEM_S = 0.2

# Tamanho do bloco de denoise e a folga entre blocos — ver docstring de
# `denoise`. 10 min mantém o pico de memória em torno de 500 MB.
BLOCO_S = 600
SOBREPOSICAO_S = 1.0

# Quantos trechos entram na mesma expressão `select` do corte. Medido em
# 28/07/2026 na live real (3h28, ~3150 trechos): uma expressão só com todos os
# `between()` encadeados derruba o ffmpeg com "Error initializing complex
# filters. Cannot allocate memory" — não é o container (sobrava memória), é o
# parser de expressão do libavfilter, e o limite é curto e EXATO: reproduzido
# isolando o mesmo arquivo, 100 termos passa, 101 falha, sempre, direto na
# inicialização do filtro (antes de decodificar um frame sequer) — é um teto
# fixo do parser, não um limite de memória que varia. O primeiro valor testado
# aqui, 150, já estava acima do teto e o lote 1 falhava igual ao arquivo
# inteiro. 80 dá margem confortável abaixo dos 100 confirmados. Cortar em
# lotes e concatenar por demuxer (sem reencode) evita o limite mantendo poucos
# processos ffmpeg.
LOTE_TRECHOS = 80


class FalhaDeMidia(RuntimeError):
    """Uma etapa da cadeia falhou. A mensagem carrega o stderr do ffmpeg."""


@dataclass(frozen=True)
class Trecho:
    inicio: float
    fim: float

    @property
    def duracao(self) -> float:
        return self.fim - self.inicio


def _rodar(cmd: list[str], *, o_que: str, timeout: int = 21600) -> str:
    """Executa e devolve stderr — é onde o ffmpeg escreve tudo que interessa."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise FalhaDeMidia(f"{o_que}: estourou {timeout}s") from exc
    if r.returncode != 0:
        cauda = (r.stderr or "").strip().splitlines()[-6:]
        raise FalhaDeMidia(f"{o_que} falhou ({r.returncode}): " + " | ".join(cauda))
    return r.stderr or ""


def duracao_de(caminho: Path) -> float:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(caminho)],
        capture_output=True, text=True,
    )
    try:
        return float((saida.stdout or "0").strip())
    except ValueError as exc:
        raise FalhaDeMidia(f"ffprobe não leu a duração de {caminho.name}") from exc


def extrair_audio(video: Path, destino: Path, *, taxa: int = 48000, canais: int = 2,
                  pre_gain_db: float | None = PRE_GAIN_DB,
                  progresso: Progresso | None = None) -> Path:
    """Tira o áudio do vídeo em WAV, já com o pre-gain aplicado.

    48 kHz estéreo é o que a cadeia de tratamento usa. Para transcrever, chame
    de novo com taxa=16000 e canais=1 e sem pre-gain: o Whisper só usa 16k mono,
    e o derivado fica 6x menor (401 MB contra 2,3 GB numa live de 3h28).
    """
    if progresso:
        progresso("extraindo_audio", f"{taxa}Hz {canais}ch")
    filtros = ["-af", f"volume={pre_gain_db}dB"] if pre_gain_db else []
    _rodar(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn",
            *filtros, "-ac", str(canais), "-ar", str(taxa),
            "-c:a", "pcm_s16le", str(destino)], o_que="extração de áudio")
    return destino


def _concatenar(partes: list[Path], destino: Path) -> Path:
    lista = destino.with_suffix(".lista.txt")
    lista.write_text("".join(f"file '{p}'\n" for p in partes), encoding="utf-8")
    _rodar(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(lista), "-c:a", "pcm_s16le", str(destino)], o_que="concatenação")
    lista.unlink(missing_ok=True)
    return destino


def denoise(wav: Path, destino_dir: Path, *, progresso: Progresso | None = None) -> Path:
    """Remove ruído de fundo com DeepFilterNet, em blocos.

    `-D` compensa o delay do modelo (STFT + lookahead). Sem essa flag o áudio
    volta deslocado alguns milissegundos e o remux entrega um vídeo fora de
    sincronia — defeito que nenhuma verificação automática pega, só o ouvido.

    **Por que em blocos:** o deep-filter carrega o arquivo inteiro em float32,
    o que para uma live de 3h28 (WAV de 2,3 GB) passa de 9 GB de RSS. Medido em
    28/07/2026: o processo morreu com SIGKILL num container de 4 GB. Fatiar
    mantém o consumo constante e independente da duração — uma live de 6h passa
    a custar o mesmo que uma de 20 min, e o job deixa de depender de quanta RAM
    sobrou na VPS naquele momento.

    Os blocos se sobrepõem em 1 s e a sobreposição é aparada do início de cada
    bloco tratado: o modelo precisa de contexto para não errar o começo, e uma
    emenda sem essa folga produz um estalo audível a cada 10 minutos.

    Custo medido nesta imagem: ~0,5x tempo real. Uma live de 3h28 leva ~1h46.
    """
    destino_dir.mkdir(parents=True, exist_ok=True)
    saida = destino_dir / wav.name
    duracao = duracao_de(wav)
    if progresso:
        progresso("denoise", f"{duracao / 60:.0f} min de áudio, "
                             f"~{duracao * 0.51 / 60:.0f} min estimados")

    if duracao <= BLOCO_S * 1.5:
        _rodar(["deep-filter", "-D", "-o", str(destino_dir), str(wav)], o_que="denoise")
        if not saida.is_file():
            raise FalhaDeMidia(f"denoise não gerou {saida}")
        return saida

    fatias_dir = destino_dir / "fatias"
    limpas_dir = destino_dir / "limpas"
    for d in (fatias_dir, limpas_dir):
        d.mkdir(parents=True, exist_ok=True)

    total = int(duracao // BLOCO_S) + 1
    prontas: list[Path] = []
    for i in range(total):
        inicio = i * BLOCO_S
        if inicio >= duracao:
            break
        recuo = SOBREPOSICAO_S if i else 0.0
        fatia = fatias_dir / f"bloco{i:04d}.wav"
        _rodar(["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio - recuo:.3f}",
                "-t", f"{BLOCO_S + recuo:.3f}", "-i", str(wav),
                "-c:a", "pcm_s16le", str(fatia)], o_que=f"fatia {i}")

        _rodar(["deep-filter", "-D", "-o", str(limpas_dir), str(fatia)],
               o_que=f"denoise do bloco {i + 1}/{total}")
        fatia.unlink(missing_ok=True)

        limpa = limpas_dir / fatia.name
        if not limpa.is_file():
            raise FalhaDeMidia(f"denoise não gerou o bloco {i}")

        # O aparo é calculado a partir da duração que o bloco REALMENTE tem, e
        # não do recuo pedido. `-ss` no input arredonda para o pacote do muxer
        # (~21 ms a 48 kHz), então aparar um valor fixo perde alguns
        # milissegundos por emenda — 0,13 s em 5 blocos, medido, o que numa
        # live de 3h28 viraria meio segundo de dessincronia acumulada no fim.
        # `atrim` corta por amostra, e a conta abaixo se autocorrige.
        desejada = min(float(BLOCO_S), duracao - inicio)
        excesso = duracao_de(limpa) - desejada
        if excesso > 0.001:
            aparada = limpas_dir / f"ok{i:04d}.wav"
            _rodar(["ffmpeg", "-y", "-v", "error", "-i", str(limpa),
                    "-af", f"atrim=start={excesso:.6f}",
                    "-c:a", "pcm_s16le", str(aparada)], o_que=f"aparo do bloco {i}")
            limpa.unlink(missing_ok=True)
            limpa = aparada
        prontas.append(limpa)
        if progresso:
            progresso("denoise", f"bloco {i + 1} de {total}")

    _concatenar(prontas, saida)
    for p in prontas:
        p.unlink(missing_ok=True)
    return saida


def _medir_loudness(wav: Path) -> dict:
    """Passo 1 do loudnorm: mede o material para o passo 2 corrigir com precisão.

    Um passe só é normalização às cegas — o filtro chuta o ganho sem conhecer o
    trecho inteiro, e o resultado erra o alvo em vários LU.
    """
    stderr = _rodar(
        ["ffmpeg", "-y", "-hide_banner", "-i", str(wav), "-af",
         f"loudnorm=I={ALVO_LUFS}:TP={ALVO_TP}:LRA={ALVO_LRA}:print_format=json",
         "-f", "null", "-"], o_que="medição de loudness", timeout=7200)
    bloco = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not bloco:
        raise FalhaDeMidia("loudnorm não devolveu a medição em JSON")
    return json.loads(bloco.group(0))


def normalizar(wav: Path, destino: Path, *, progresso: Progresso | None = None) -> Path:
    """loudnorm em dois passes até -14 LUFS."""
    if progresso:
        progresso("loudnorm", "passo 1 de 2 (medindo)")
    m = _medir_loudness(wav)
    if progresso:
        progresso("loudnorm", f"passo 2 de 2 (medido: {m.get('input_i')} LUFS, "
                              f"pico {m.get('input_tp')} dBTP)")
    filtro = (
        f"loudnorm=I={ALVO_LUFS}:TP={ALVO_TP}:LRA={ALVO_LRA}"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}:linear=true:print_format=summary"
    )
    _rodar(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", filtro,
            "-ar", "48000", "-c:a", "pcm_s16le", str(destino)],
           o_que="normalização", timeout=7200)
    return destino


def remuxar(video: Path, wav: Path, destino: Path, *,
            progresso: Progresso | None = None) -> Path:
    """Devolve o áudio tratado ao vídeo, sem reencodar a imagem."""
    if progresso:
        progresso("remux", "copiando vídeo, reencodando só o áudio")
    _rodar(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(wav),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-shortest", str(destino)],
           o_que="remux")
    return destino


def detectar_silencio(midia: Path, *, limiar_db: int = LIMIAR_SILENCIO_DB,
                      minimo_s: float = SILENCIO_MINIMO_S,
                      progresso: Progresso | None = None) -> list[Trecho]:
    """Lista os intervalos de silêncio.

    Roda sempre no áudio JÁ tratado — ver o docstring do módulo.
    """
    if progresso:
        progresso("detectando_silencio", f"limiar {limiar_db}dB, mínimo {minimo_s}s")
    stderr = _rodar(
        ["ffmpeg", "-hide_banner", "-i", str(midia), "-af",
         f"silencedetect=noise={limiar_db}dB:d={minimo_s}", "-f", "null", "-"],
        o_que="detecção de silêncio", timeout=7200)

    silencios: list[Trecho] = []
    inicio: float | None = None
    for m in re.finditer(r"silence_(start|end):\s*(-?[\d.]+)", stderr):
        marca, valor = m.group(1), float(m.group(2))
        if marca == "start":
            inicio = valor
        elif inicio is not None:
            silencios.append(Trecho(max(0.0, inicio), valor))
            inicio = None
    # Silêncio aberto no fim do arquivo: o ffmpeg não emite silence_end quando o
    # material acaba em silêncio, e ignorar isso deixa a cauda morta na peça.
    if inicio is not None:
        silencios.append(Trecho(max(0.0, inicio), duracao_de(midia)))
    return silencios


def trechos_com_fala(silencios: Iterable[Trecho], duracao: float, *,
                     margem: float = MARGEM_S) -> list[Trecho]:
    """Inverte a lista de silêncios: o que sobra é o que vai ao ar.

    A margem devolve um pedaço do silêncio a cada ponta, senão o corte come o
    ataque da primeira sílaba. Trechos que ficam menores que a própria margem
    são descartados — um resto de 0,1 s no meio da peça é ruído de edição.
    """
    trechos: list[Trecho] = []
    cursor = 0.0
    for s in sorted(silencios, key=lambda t: t.inicio):
        fim = min(s.inicio + margem, duracao)
        if fim - cursor > margem:
            trechos.append(Trecho(cursor, fim))
        cursor = max(cursor, s.fim - margem)
    if duracao - cursor > margem:
        trechos.append(Trecho(cursor, duracao))
    return trechos


def trechos_a_manter(remover: Iterable[Trecho], duracao: float) -> list[Trecho]:
    """Inverte uma lista de trechos A REMOVER (não de silêncio) no que
    sobra — usada pela Fase 1B (corte editorial): o modelo marca o que
    cortar, isto devolve o que fica. Sem margem de segurança (diferente de
    `trechos_com_fala`): os timestamps aqui já vêm de uma decisão editorial
    explícita, não de detecção automática de silêncio, então não há ataque
    de sílaba a proteger.
    """
    trechos: list[Trecho] = []
    cursor = 0.0
    for t in sorted(remover, key=lambda x: x.inicio):
        inicio = max(0.0, min(t.inicio, duracao))
        fim = max(0.0, min(t.fim, duracao))
        if inicio > cursor:
            trechos.append(Trecho(cursor, inicio))
        cursor = max(cursor, fim)
    if duracao > cursor:
        trechos.append(Trecho(cursor, duracao))
    return trechos


def _cortar_lote(midia: Path, trechos: list[Trecho], destino: Path) -> Path:
    """Um único corte por `select`/`aselect`, para um lote de até
    `LOTE_TRECHOS` trechos. O filtro vai por `-filter_complex_script`, não
    pela linha de comando: mesmo um lote de 150 trechos passa do que é
    legível como argumento, e isso ainda cabe no ARG_MAX.

    `select` + `setpts` no vídeo e `aselect` + `asetpts` no áudio precisam andar
    juntos; mexer em um só entrega uma peça com áudio e imagem em tempos
    diferentes, que é pior que não cortar.
    """
    expr = "+".join(f"between(t,{t.inicio:.3f},{t.fim:.3f})" for t in trechos)
    script = destino.with_suffix(".filtro.txt")
    script.write_text(
        f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB[v];"
        f"[0:a]aselect='{expr}',asetpts=N/SR/TB[a]",
        encoding="utf-8",
    )
    _rodar(["ffmpeg", "-y", "-v", "error", "-i", str(midia),
            "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "160k", str(destino)], o_que="corte de lote")
    script.unlink(missing_ok=True)
    return destino


def cortar(midia: Path, trechos: list[Trecho], destino: Path, *,
           progresso: Progresso | None = None) -> Path:
    """Mantém só os trechos indicados, num arquivo contínuo.

    Trechos são cortados em lotes de `LOTE_TRECHOS` (ver a constante) e os
    lotes concatenados por demuxer, sem reencode — ver o motivo no comentário
    da constante. Para uma peça curta com um único lote, é exatamente o
    comportamento anterior (um corte só, sem concatenação).
    """
    if not trechos:
        raise FalhaDeMidia("nenhum trecho com fala — nada a cortar")
    if progresso:
        total = sum(t.duracao for t in trechos)
        progresso("cortando", f"{len(trechos)} trechos, {total / 60:.1f} min de saída")

    lotes = [trechos[i:i + LOTE_TRECHOS] for i in range(0, len(trechos), LOTE_TRECHOS)]
    if len(lotes) == 1:
        return _cortar_lote(midia, lotes[0], destino)

    lotes_dir = destino.parent / f"{destino.stem}_lotes"
    lotes_dir.mkdir(parents=True, exist_ok=True)
    try:
        linhas = []
        for i, lote in enumerate(lotes):
            if progresso:
                progresso("cortando", f"lote {i + 1} de {len(lotes)}")
            saida_lote = lotes_dir / f"lote{i:04d}.mp4"
            _cortar_lote(midia, lote, saida_lote)
            linhas.append(f"file '{saida_lote.resolve()}'")

        lista = lotes_dir / "lista.txt"
        lista.write_text("\n".join(linhas), encoding="utf-8")

        if progresso:
            progresso("concatenando", f"{len(lotes)} lotes")
        _rodar(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(lista), "-c", "copy", str(destino)], o_que="concatenação dos lotes")
    finally:
        shutil.rmtree(lotes_dir, ignore_errors=True)
    return destino


def primeiro_corte(video: Path, saida: Path, *, trabalho: Path,
                   progresso: Progresso | None = None) -> dict:
    """A cadeia inteira da Fase 1A, na ordem correta.

    Limpa cada intermediário assim que a etapa seguinte não precisa mais dele.
    O WAV de 48k de uma live de 3h28 tem 2,3 GB, e segurar todos até o fim do
    job enche o disco da VPS antes da última etapa.
    """
    trabalho.mkdir(parents=True, exist_ok=True)
    duracao_original = duracao_de(video)

    bruto = extrair_audio(video, trabalho / "audio.wav", progresso=progresso)
    limpo = denoise(bruto, trabalho / "df", progresso=progresso)
    bruto.unlink(missing_ok=True)

    normalizado = normalizar(limpo, trabalho / "final.wav", progresso=progresso)
    limpo.unlink(missing_ok=True)

    tratado = remuxar(video, normalizado, trabalho / "tratado.mp4", progresso=progresso)
    normalizado.unlink(missing_ok=True)

    silencios = detectar_silencio(tratado, progresso=progresso)
    trechos = trechos_com_fala(silencios, duracao_de(tratado))
    cortar(tratado, trechos, saida, progresso=progresso)
    tratado.unlink(missing_ok=True)

    duracao_final = duracao_de(saida)
    return {
        "duracao_original_s": round(duracao_original, 2),
        "duracao_final_s": round(duracao_final, 2),
        "cortado_s": round(duracao_original - duracao_final, 2),
        "cortado_pct": round(100 * (1 - duracao_final / duracao_original), 1)
        if duracao_original else None,
        "silencios": len(silencios),
        "trechos": len(trechos),
    }


def aplicar_corte_editorial(video: Path, cortes_aprovados: list[dict], saida: Path, *,
                            progresso: Progresso | None = None) -> dict:
    """Fase 1B, depois da aprovação humana: remove os trechos que o modelo
    propôs e o humano aprovou (na página de revisão via /shares) — nunca
    os que o modelo só sugeriu. `cortes_aprovados` é a lista já filtrada
    pelo humano, no formato [{"inicio": float, "fim": float}, ...].

    Não recalcula nada além disso: quem decidiu o que cortar foi o gate,
    não este código.
    """
    if progresso:
        progresso("aplicando_corte_editorial", f"{len(cortes_aprovados)} trecho(s) aprovado(s)")

    duracao_original = duracao_de(video)
    remover = [Trecho(float(c["inicio"]), float(c["fim"])) for c in cortes_aprovados]
    manter = trechos_a_manter(remover, duracao_original)

    if not manter:
        raise FalhaDeMidia("corte editorial aprovado removeria o vídeo inteiro — nada a manter")

    cortar(video, manter, saida, progresso=progresso)
    duracao_final = duracao_de(saida)

    return {
        "duracao_original_s": round(duracao_original, 2),
        "duracao_final_s": round(duracao_final, 2),
        "cortado_s": round(duracao_original - duracao_final, 2),
        "cortado_pct": round(100 * (1 - duracao_final / duracao_original), 1)
        if duracao_original else None,
        "cortes_aplicados": len(remover),
    }
