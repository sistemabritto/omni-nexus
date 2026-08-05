"""
tests/goals/test_gate_recusa_texto_longo.py

O laço de aprovação que nunca convergia (madrugada de 05/08/2026).

A esteira do blog corta o texto antes de propor, mas ela não é o único caminho:
agente que publica a partir de um ticket escreve direto e não passa por corte
nenhum. O resultado, medido em produção:

    #129  x        984 bytes (teto 266)
    #131  x        927 bytes
    #127  threads  693 bytes (teto 475)

Cada um levava `400 {"provider":"x","message":"post is too long"}` do Postiz. O
ticket voltava a `in_progress`, o heartbeat retentava, abria gate novo
(`publish:<ticket>:1`, `:2`, `:3`, `:4`), o humano aprovava de madrugada e
falhava de novo. Quatro rodadas no mesmo post, quatro aprovações gastas à toa.

Duas barreiras fecham isso:
  1. `_recusar_se_estoura` — o gate não nasce (fail-fast, o agente reescreve)
  2. `_run_publish_action` — não gasta chamada ao Postiz que já sabemos que 400

Run:
    pytest tests/goals/test_gate_recusa_texto_longo.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))

from routes.approvals import _recusar_se_estoura  # noqa: E402
import ghost_social_bridge as bridge  # noqa: E402


@pytest.fixture(autouse=True)
def contexto_flask():
    """`jsonify` exige app context. Um Flask vazio basta — a função sob teste
    não toca em banco nem em config."""
    import flask

    app = flask.Flask(__name__)
    with app.app_context():
        yield


def _payload(target: str, conteudo: str) -> dict:
    return {"outcome": {"publish_target": target, "publish_content": conteudo}}


# ── a barreira na criação do gate ────────────────────────────────────────

@pytest.mark.parametrize("target,tamanho", [("x", 984), ("x", 927), ("threads", 693)])
def test_recusa_os_tamanhos_que_o_postiz_recusou_de_verdade(target, tamanho):
    """Os três casos reais da madrugada, reproduzidos pelo tamanho."""
    resposta = _recusar_se_estoura(_payload(target, "a" * tamanho))
    assert resposta is not None, f"{tamanho} bytes em {target} tinha de ser recusado"
    corpo, status = resposta
    assert status == 400
    dados = corpo.get_json()
    assert dados["error"] == "publish_content_too_long"
    # O agente precisa do número para reescrever, não de um "inválido".
    assert dados["bytes"] == tamanho
    assert dados["max_bytes"] == bridge.teto_de(target)


def test_aceita_o_que_cabe():
    assert _recusar_se_estoura(_payload("x", "a" * bridge.teto_de("x"))) is None
    assert _recusar_se_estoura(_payload("threads", "a" * bridge.teto_de("threads"))) is None


def test_mede_em_bytes_e_nao_em_caracteres():
    """A régua do validador que está no caminho conta "ç" como 2.

    Um post de 271 caracteres foi recusado em produção e um de 272 passou — o
    primeiro tinha quatro acentos.
    """
    teto = bridge.teto_de("x")
    acentuado = "ç" * ((teto // 2) + 1)          # cabe em caracteres, estoura em bytes
    assert len(acentuado) < teto
    assert bridge.medida(acentuado) > teto
    assert _recusar_se_estoura(_payload("x", acentuado)) is not None


def test_blog_nao_tem_limite_de_tamanho():
    """O artigo vai para o Ghost, não para o Postiz — cortar aqui seria mutilar
    o conteúdo por uma regra que não se aplica a ele."""
    assert _recusar_se_estoura(_payload("blog", "a" * 50_000)) is None


def test_payload_sem_conteudo_nao_e_barrado_aqui():
    """Conteúdo vazio tem erro próprio, mais específico, adiante no fluxo."""
    assert _recusar_se_estoura(_payload("x", "")) is None
    assert _recusar_se_estoura({}) is None
    assert _recusar_se_estoura({"outcome": {}}) is None


def test_alvo_desconhecido_passa_batido():
    """Rede fora de LIMITES não tem régua nossa — inventar uma barraria
    publicação legítima."""
    assert _recusar_se_estoura(_payload("mastodon", "a" * 5000)) is None


# ── a barreira antes de chamar o Postiz ──────────────────────────────────

def test_run_publish_action_nao_gasta_chamada_ao_postiz():
    """Cards abertos ANTES desta correção continuam existindo. Aprovar um deles
    não pode virar uma chamada que já sabemos que volta 400."""
    fonte = (ROOT / "dashboard" / "backend" / "heartbeat_outcome.py").read_text(encoding="utf-8")
    trecho = fonte.split("def _run_publish_action")[1].split("PostizClient.from_env()")[0]
    assert "teto_de(target)" in trecho
    assert "medida(content)" in trecho
    # Antes do blog, senão o artigo seria medido por uma régua de rede social.
    assert trecho.index("teto_de(target)") < trecho.index('if target == "blog"')


def test_a_recusa_diz_o_numero_e_o_que_fazer():
    """"Inválido" manda o agente adivinhar; o número e o teto ele usa."""
    corpo, _ = _recusar_se_estoura(_payload("x", "a" * 900))
    hint = corpo.get_json()["hint"]
    assert "bytes" in hint
    assert str(bridge.teto_de("x")) in hint
    assert "acento" in hint.lower()
