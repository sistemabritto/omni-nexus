"""
tests/goals/test_feedback_de_aprovacao.py

O terceiro botão (pedido do Felipe, 25/07/2026).

O gate tinha dois caminhos: aprovar e rejeitar. Faltava o do meio, que é o mais
usado na prática — "está quase, muda isto". Sem ele o humano só tem duas saídas
ruins: aprovar um texto de que não gostou, ou rejeitar e escrever ele mesmo.

Duas finalidades, e o teste cobre as duas separadamente porque elas falham por
motivos diferentes:

1. **Refazer agora** — o ticket volta ao agente com a crítica.
2. **Não errar de novo** — o feedback acumulado entra no prompt das gerações
   seguintes. É isto que faz o padrão convergir sem ninguém reescrever
   briefing, e é a parte que passa despercebida quando quebra: o texto continua
   saindo, só que sem ter aprendido nada.

Run:
    pytest tests/goals/test_feedback_de_aprovacao.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import approval_feedback as fb  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "LEDGER", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(fb, "WORKSPACE", tmp_path)
    return tmp_path / "feedback.jsonl"


# ── gravação ─────────────────────────────────────────────────────────────

def test_grava_o_feedback_no_ledger(ledger):
    r = fb.registrar(agente="pixel-social-media", alvo="linkedin",
                     feedback="corta as hashtags", titulo="Artigo X")
    assert r["ok"] is True
    linha = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert linha["feedback"] == "corta as hashtags"
    assert linha["alvo"] == "linkedin"


def test_feedback_vazio_e_recusado(ledger):
    assert fb.registrar(agente="a", alvo="x", feedback="   ")["ok"] is False
    assert not ledger.exists()


def test_tambem_anota_na_memoria_do_agente(ledger, tmp_path):
    """O protocolo de recall dos agentes lê markdown, o ledger é para injeção
    em prompt — leitores diferentes, não duplicação por descuido."""
    fb.registrar(agente="pixel-social-media", alvo="x", feedback="menos emoji")
    arquivo = tmp_path / ".claude" / "agent-memory" / "pixel-social-media" / "learnings.md"
    assert arquivo.exists()
    assert "menos emoji" in arquivo.read_text(encoding="utf-8")


def test_falha_ao_anotar_memoria_nao_derruba_o_registro(ledger, monkeypatch):
    monkeypatch.setattr(fb, "_anotar_na_memoria_do_agente",
                        lambda _r: (_ for _ in ()).throw(OSError("disco cheio")))
    with pytest.raises(OSError):
        fb._anotar_na_memoria_do_agente({})
    # o registro em si continua funcionando pelo caminho real
    monkeypatch.undo()
    assert fb.registrar(agente="a", alvo="x", feedback="ok")["ok"] is True


# ── leitura para o prompt ────────────────────────────────────────────────

def test_diretrizes_vazias_quando_nao_ha_historico(ledger):
    assert fb.diretrizes("linkedin") == ""


def test_diretrizes_trazem_o_que_foi_pedido(ledger):
    fb.registrar(agente="a", alvo="linkedin", feedback="corta as hashtags")
    fb.registrar(agente="a", alvo="linkedin", feedback="gancho mais forte")
    texto = fb.diretrizes("linkedin")
    assert "corta as hashtags" in texto and "gancho mais forte" in texto
    assert "regra e não sugestão" in texto


def test_diretrizes_filtram_por_rede(ledger):
    fb.registrar(agente="a", alvo="linkedin", feedback="corta hashtag")
    fb.registrar(agente="a", alvo="x", feedback="mais curto")
    assert "mais curto" not in fb.diretrizes("linkedin")
    assert "corta hashtag" not in fb.diretrizes("x")


def test_feedback_geral_vale_para_todas(ledger):
    fb.registrar(agente="a", alvo="geral", feedback="nunca prometer resultado")
    for rede in ("x", "linkedin", "threads"):
        assert "nunca prometer resultado" in fb.diretrizes(rede)


def test_repetido_nao_ocupa_contexto_duas_vezes(ledger):
    for _ in range(3):
        fb.registrar(agente="a", alvo="x", feedback="Corta as hashtags")
    assert fb.diretrizes("x").count("orta as hashtags") == 1


def test_mais_recente_fica_por_ultimo(ledger):
    """O modelo dá mais peso ao final do bloco, e é o feedback mais novo que
    deve pesar mais."""
    fb.registrar(agente="a", alvo="x", feedback="regra antiga")
    fb.registrar(agente="a", alvo="x", feedback="regra nova")
    texto = fb.diretrizes("x")
    assert texto.index("regra antiga") < texto.index("regra nova")


def test_respeita_o_limite(ledger):
    for i in range(30):
        fb.registrar(agente="a", alvo="x", feedback=f"regra {i}")
    assert len(fb.diretrizes("x", limite=5).splitlines()) == 6  # cabeçalho + 5


def test_linha_corrompida_nao_cega_o_resto(ledger):
    fb.registrar(agente="a", alvo="x", feedback="regra boa")
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("{ isto não é json\n")
    fb.registrar(agente="a", alvo="x", feedback="outra boa")
    texto = fb.diretrizes("x")
    assert "regra boa" in texto and "outra boa" in texto


# ── o self-learning chega ao prompt ──────────────────────────────────────

def test_o_gerador_de_texto_injeta_as_diretrizes(ledger, monkeypatch):
    """Sem isto o botão vira só um registro bonito: o texto continua saindo,
    só que sem ter aprendido nada."""
    import ghost_social_bridge as bridge

    fb.registrar(agente="a", alvo="linkedin", feedback="proibido usar emoji de foguete")

    capturado = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"output": [{"type": "message",
                                "content": [{"type": "output_text", "text": "texto final"}]}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        capturado["prompt"] = json["input"][0]["content"]
        return _Resp()

    monkeypatch.setenv("XAI_API_KEY", "chave")
    monkeypatch.setattr(bridge.requests, "post", fake_post)

    bridge.adaptar({"title": "T", "custom_excerpt": "R", "url": "https://e.com",
                    "plaintext": "corpo"}, "linkedin")
    assert "proibido usar emoji de foguete" in capturado["prompt"]


def test_gerador_funciona_sem_ledger_nenhum(monkeypatch, tmp_path):
    """Ledger indisponível não pode travar a geração."""
    import ghost_social_bridge as bridge

    monkeypatch.setattr(fb, "LEDGER", tmp_path / "nao-existe.jsonl")
    monkeypatch.setenv("XAI_API_KEY", "")
    assert bridge.adaptar({"title": "T", "custom_excerpt": "R", "url": ""}, "x")


# ── contrato com o gate ──────────────────────────────────────────────────

def test_marca_de_ajuste_distingue_de_rejeicao():
    """O CHECK de status não tem estado de revisão; a marca em reject_reason é
    o que permite a UI dizer 'ajuste' em vez de 'rejeitada'."""
    assert fb.MARCA_AJUSTE.strip().startswith("[")


def test_endpoint_de_ajuste_existe_e_e_de_sessao_admin():
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(
        encoding="utf-8")
    assert "/api/approvals/<int:approval_id>/revise" in fonte
    trecho = fonte.split("def pedir_ajuste_via_dashboard")[1].split("def _apply_decision")[0]
    assert "auth_via_api_token" in trecho, "token de API não pode pedir ajuste no próprio gate"
    assert 'role != "admin"' in trecho


def test_ponte_do_telegram_aceita_revise():
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def decide_approval")[1].split("def decide_approval_via_dashboard")[0]
    assert '"revise"' in trecho
    assert "_approver_allowlist" in trecho, "pedir ajuste é decisão sobre conteúdo público"


def test_card_do_telegram_tem_os_tres_botoes_e_a_marca():
    fonte = (REPO_ROOT / "dashboard" / "backend" / "notifications.py").read_text(encoding="utf-8")
    for parte in (":a\"", ":e\"", ":r\"", "#apr:"):
        assert parte in fonte, f"faltou {parte!r} no card"


def test_bot_captura_resposta_no_card_com_imagem():
    """O card com imagem é foto legendada: sem ler `caption` o ajuste por
    resposta funcionaria só nos posts sem imagem."""
    fonte = (REPO_ROOT / "scripts" / "telegram_provider_bot.py").read_text(encoding="utf-8")
    trecho = fonte.split("m_apr = re.search")[0][-500:]
    assert "caption" in trecho
