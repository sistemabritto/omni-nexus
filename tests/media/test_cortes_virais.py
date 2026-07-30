"""
tests/media/test_cortes_virais.py

2026-07-29 — Fase 1C: cortes verticais curtos com legenda karaokê e zoom.

Validado com dado real antes de escrever este arquivo (não só mockado): um
trecho de 30s do vídeo da Fase 1A de hoje virou 1080x1920 h264+aac com
legenda palavra-a-palavra sincronizada e zoom aplicado, transcrito por
palavra via Groq de verdade. Achado real no processo: o material fonte é
gravação de call com tela compartilhada, então o crop centralizado pega
bastante chrome de UI (abas do navegador) — limitação do material, não do
código; registrado no docstring de `renderizar_corte_viral`.

Run:
    pytest tests/media/test_cortes_virais.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import cortes_virais  # noqa: E402
from cortes_virais import (  # noqa: E402
    propor_cortes_virais,
    formatar_para_selecao,
    montar_legenda_ass,
    renderizar_corte_viral,
    _agrupar_em_linhas,
    _agrupar_legenda,
    _ass_timestamp,
    DURACAO_MIN_S,
    DURACAO_MAX_S,
)
from transcricao import Palavra


def _palavra(inicio, fim, texto):
    return Palavra(inicio=inicio, fim=fim, texto=texto)


# ── agrupamento e formatação ──────────────────────────────────────────────

def test_agrupar_em_linhas_junta_ate_a_janela():
    palavras = [_palavra(0.0, 1.0, "a"), _palavra(1.0, 2.0, "b"), _palavra(8.0, 9.0, "c")]
    linhas = _agrupar_em_linhas(palavras, janela_s=6.0)
    assert len(linhas) == 2
    assert linhas[0][2] == "a b"
    assert linhas[1][2] == "c"


def test_formatar_para_selecao_tem_timestamps():
    palavras = [_palavra(10.0, 10.5, "oi"), _palavra(10.5, 11.0, "mundo")]
    texto = formatar_para_selecao(palavras)
    assert texto == "[10-11] oi mundo"


def test_agrupar_legenda_respeita_max_palavras():
    palavras = [_palavra(i, i + 0.5, str(i)) for i in range(10)]
    linhas = _agrupar_legenda(palavras, max_palavras=4)
    assert len(linhas) == 3
    assert len(linhas[0].palavras) == 4
    assert len(linhas[-1].palavras) == 2


def test_ass_timestamp_formato():
    assert _ass_timestamp(0.0) == "0:00:00.00"
    assert _ass_timestamp(65.5) == "0:01:05.50"
    assert _ass_timestamp(3661.25) == "1:01:01.25"


# ── legenda .ass ────────────────────────────────────────────────────────

def test_legenda_ass_tem_tag_karaoke_por_palavra(tmp_path):
    palavras = [_palavra(10.0, 10.3, "isso"), _palavra(10.3, 10.9, "funciona")]
    destino = montar_legenda_ass(palavras, offset=10.0, destino=tmp_path / "l.ass")
    conteudo = destino.read_text()
    assert r"{\k30}isso" in conteudo
    assert r"{\k60}funciona" in conteudo


def test_legenda_ass_respeita_safe_zone_das_redes(tmp_path):
    """Feedback real em 30/07/2026: legenda conflitando com a UI nativa do
    TikTok/Reels/Shorts (legenda do próprio app, ícones de ação, @usuário) —
    MarginV baixo demais. LEGENDA_MARGIN_V precisa deixar folga real."""
    palavras = [_palavra(0.0, 0.5, "oi")]
    destino = montar_legenda_ass(palavras, offset=0.0, destino=tmp_path / "l.ass")
    conteudo = destino.read_text()
    assert f",{cortes_virais.LEGENDA_MARGIN_V},1" in conteudo
    assert cortes_virais.LEGENDA_MARGIN_V >= 500  # >~26% da altura, fora da faixa de UI nativa


def test_legenda_ass_escapa_caracteres_de_controle(tmp_path):
    palavras = [_palavra(0.0, 0.5, "{teste}"), _palavra(0.5, 1.0, "a\\b")]
    destino = montar_legenda_ass(palavras, offset=0.0, destino=tmp_path / "l.ass")
    conteudo = destino.read_text()
    # sobra só o texto sem chave/barra — senão vira tag ASS ou path quebrado
    assert "{teste}" not in conteudo
    assert "a\\b" not in conteudo


def test_legenda_ass_ignora_palavra_antes_do_offset(tmp_path):
    """Palavra que termina antes do início do corte não deve aparecer —
    sobraria legenda "fantasma" no primeiro frame do trecho."""
    palavras = [_palavra(0.0, 5.0, "antes"), _palavra(10.0, 10.5, "dentro")]
    destino = montar_legenda_ass(palavras, offset=10.0, destino=tmp_path / "l.ass")
    conteudo = destino.read_text()
    assert "antes" not in conteudo
    assert "dentro" in conteudo


# ── seleção via modelo ─────────────────────────────────────────────────────

def _resultado_modelo(payload: str):
    return {"status": "success", "output": payload}


def test_propor_cortes_filtra_duracao_fora_da_faixa():
    palavras = [_palavra(0.0, 200.0, "x")]
    curto_demais = f'[{{"inicio": 0, "fim": {DURACAO_MIN_S - 1}, "titulo": "a"}}]'
    longo_demais = f'[{{"inicio": 0, "fim": {DURACAO_MAX_S + 1}, "titulo": "b"}}]'
    valido = f'[{{"inicio": 0, "fim": {(DURACAO_MIN_S + DURACAO_MAX_S) / 2}, "titulo": "c"}}]'

    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(curto_demais)):
        assert propor_cortes_virais(palavras, cwd=Path(".")) == []
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(longo_demais)):
        assert propor_cortes_virais(palavras, cwd=Path(".")) == []
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(valido)):
        cortes = propor_cortes_virais(palavras, cwd=Path("."))
    assert len(cortes) == 1
    assert cortes[0]["titulo"] == "c"


def test_propor_cortes_remove_sobreposicao():
    palavras = [_palavra(0.0, 200.0, "x")]
    payload = (
        '[{"inicio": 0, "fim": 40, "titulo": "primeiro"},'
        ' {"inicio": 20, "fim": 60, "titulo": "sobrepoe"}]'
    )
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(payload)):
        cortes = propor_cortes_virais(palavras, cwd=Path("."))
    assert len(cortes) == 1
    assert cortes[0]["titulo"] == "primeiro"


def test_propor_cortes_respeita_max_cortes():
    palavras = [_palavra(0.0, 1000.0, "x")]
    itens = [f'{{"inicio": {i * 100}, "fim": {i * 100 + 30}, "titulo": "c{i}"}}' for i in range(10)]
    payload = "[" + ",".join(itens) + "]"
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(payload)):
        cortes = propor_cortes_virais(palavras, cwd=Path("."), max_cortes=3)
    assert len(cortes) == 3


def test_propor_cortes_status_de_erro_propaga():
    with patch("cortes_virais.invoke_with_fallback", return_value={"status": "error", "error": "falhou"}):
        try:
            propor_cortes_virais([_palavra(0, 10, "x")], cwd=Path("."))
            assert False, "deveria ter levantado"
        except RuntimeError as e:
            assert "falhou" in str(e)


def test_propor_cortes_lista_vazia_e_valida():
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo("[]")):
        assert propor_cortes_virais([_palavra(0, 10, "x")], cwd=Path(".")) == []


def test_propor_cortes_aceita_array_com_escape_extra_estilo_string_json():
    """Achado ao vivo em 29/07/2026, job real contra o vídeo de 3h02: o
    modelo devolveu o array com um nível extra de escape, como se tivesse
    serializado a resposta duas vezes (\\" em vez de ", \\n em vez de quebra
    de linha real). json.loads rejeitava com "Expecting ',' delimiter"."""
    payload = '[{\\"inicio\\": 325, \\"fim\\": 356, \\"titulo\\": \\"Quem monetiza com IA\\", \\"motivo\\": \\"teste com acento é ção\\"}]'
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(payload)):
        cortes = propor_cortes_virais([_palavra(0.0, 400.0, "x")], cwd=Path("."))
    assert len(cortes) == 1
    assert cortes[0]["titulo"] == "Quem monetiza com IA"
    assert cortes[0]["motivo"] == "teste com acento é ção"


def test_propor_cortes_aceita_aspas_simples_estilo_dict_python():
    """Achado ao vivo em 29/07/2026: o modelo às vezes devolve sintaxe de
    dict Python (aspas simples) em vez de JSON estrito — json.loads rejeita
    com "Expecting property name enclosed in double quotes"."""
    payload = "[{'inicio': 0, 'fim': 40, 'titulo': 'corte legal'}]"
    with patch("cortes_virais.invoke_with_fallback", return_value=_resultado_modelo(payload)):
        cortes = propor_cortes_virais([_palavra(0.0, 200.0, "x")], cwd=Path("."))
    assert len(cortes) == 1
    assert cortes[0]["titulo"] == "corte legal"


# ── renderização (ffmpeg mockado) ──────────────────────────────────────────

def test_renderizar_faz_duas_passadas_composicao_depois_zoom_legenda(tmp_path):
    """Duas chamadas de ffmpeg, não uma — achado ao vivo em 29/07/2026:
    zoompan reavalia toda a cadeia de filtros anteriores por frame, e com
    blur+overlay antes dele isso nunca terminava. Compor (blur+avatar) e só
    depois aplicar zoom+legenda no resultado paga cada filtro uma vez só."""
    video = tmp_path / "in.mp4"
    saida = tmp_path / "out.mp4"
    corte = {"inicio": 5.0, "fim": 35.0, "titulo": "teste"}
    palavras = [_palavra(6.0, 6.5, "oi")]
    (tmp_path / "avatar.png").touch()  # cache hit — pula o ffmpeg de preparo do avatar

    def _simula_ffmpeg(cmd, **kwargs):
        Path(cmd[-1]).touch()  # _rodar mockado — simula o arquivo de saída daquela chamada
        return ""

    with patch.object(cortes_virais, "_rodar", side_effect=_simula_ffmpeg) as mock_rodar:
        resultado = renderizar_corte_viral(video, corte, palavras, saida, trabalho=tmp_path)

    assert mock_rodar.call_count == 2
    composicao, zoom_legenda = (c.args[0] for c in mock_rodar.call_args_list)

    filtro_composicao = composicao[composicao.index("-filter_complex") + 1]
    assert "gblur=" in filtro_composicao  # fundo desfocado, não crop cru
    assert "overlay=" in filtro_composicao  # frame completo + avatar sobrepostos
    assert "overlay=(W-w)/2:" in filtro_composicao  # avatar centralizado no topo, não no canto
    assert f"text='{cortes_virais.ARROBA_MARCA}'" in filtro_composicao  # @sistemabritto embaixo do avatar
    assert "zoompan=" not in filtro_composicao  # zoompan NÃO entra nesta passada
    assert "-loop" in composicao and "1" in composicao  # avatar (imagem estática) repete por todo o clipe
    assert "-shortest" in composicao  # senão o -loop 1 do avatar nunca termina o encode sozinho
    assert "-map" in composicao and "[out]" in composicao

    filtro_zoom = zoom_legenda[zoom_legenda.index("-vf") + 1]
    assert "zoompan=" in filtro_zoom
    assert "sin(2*PI*on/" in filtro_zoom  # pulso periódico de zoom, não só rampa monotônica
    assert "subtitles=" in filtro_zoom
    assert "gblur=" not in filtro_zoom  # blur já foi feito na primeira passada

    assert resultado["largura"] == 1080
    assert resultado["altura"] == 1920
    assert resultado["duracao_s"] == 30.0


def test_preparar_avatar_circular_cacheia_por_destino(tmp_path):
    origem = tmp_path / "foto.jpg"
    destino = tmp_path / "avatar.png"
    destino.touch()  # já existe — não deve chamar ffmpeg

    with patch.object(cortes_virais, "_rodar") as mock_rodar:
        resultado = cortes_virais.preparar_avatar_circular(origem, destino)

    mock_rodar.assert_not_called()
    assert resultado == destino


def test_preparar_avatar_circular_gera_quando_nao_existe(tmp_path):
    origem = tmp_path / "foto.jpg"
    destino = tmp_path / "sub" / "avatar.png"

    def _simula_ffmpeg(cmd, **kwargs):
        destino.touch()  # _rodar mockado — simula o arquivo que o ffmpeg real geraria
        return ""

    with patch.object(cortes_virais, "_rodar", side_effect=_simula_ffmpeg) as mock_rodar:
        resultado = cortes_virais.preparar_avatar_circular(origem, destino, diametro=200)

    cmd = mock_rodar.call_args.args[0]
    filtro = cmd[cmd.index("-vf") + 1]
    assert "geq=" in filtro
    assert "crop=200:200" in filtro
    # viés pro topo, não centrado — feedback real em 30/07/2026 ("avatar tá
    # cropado quando não deveria"): crop centrado cortava testa do rosto.
    assert "crop=200:200:(iw-200)/2:(ih-200)*" in filtro
    assert resultado == destino


def test_renderizar_falha_se_ffmpeg_nao_gerar_arquivo(tmp_path):
    video = tmp_path / "in.mp4"
    saida = tmp_path / "nao_existe.mp4"
    corte = {"inicio": 0.0, "fim": 25.0, "titulo": "x"}

    with patch.object(cortes_virais, "_rodar", return_value=""):
        try:
            renderizar_corte_viral(video, corte, [], saida, trabalho=tmp_path)
            assert False, "deveria ter levantado FalhaDeMidia"
        except Exception as e:
            assert "não gerou" in str(e)
