"""
tests/goals/test_derivacao_de_agendado.py

2026-07-27 — o artigo agendado que nunca chegou às redes.

Os dois artigos do dia foram aprovados de manhã com `publish_at` para 13h e
18h BRT. O Ghost publicou os dois no horário. Nenhum post de X, LinkedIn ou
Threads existiu, e nada no sistema acusou erro: `_run_blog_publish` só deriva
as redes quando publica na hora (`status != "scheduled"`), e o webhook
`post.published` que cobriria o caso não está cadastrado no Ghost — a chave de
Admin API devolve 403 no endpoint de integrações, então criar o webhook exige
alguém logado no painel.

Estes testes guardam as duas peças da correção: o varredor que encontra o
artigo órfão e a idempotência que impede os três caminhos de derivação de
abrirem a mesma aprovação três vezes.

Run:
    pytest tests/goals/test_derivacao_de_agendado.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_social_bridge as bridge  # noqa: E402


def _agora(horas_atras: float) -> str:
    quando = datetime.now(timezone.utc) - timedelta(hours=horas_atras)
    return quando.isoformat().replace("+00:00", "Z")


class _Evo:
    """Dublê do EvoClient: devolve as aprovações que o teste declarar."""

    def __init__(self, approvals=None):
        self.approvals = approvals or []
        self.posts = []

    def get(self, rota, params=None):
        assert rota == "/api/approvals"
        return {"approvals": self.approvals}

    def post(self, rota, corpo=None):
        self.posts.append((rota, corpo))
        return {"id": f"tk-{len(self.posts)}"}


def _aprovacao(source_id: str, rede: str, status: str = "pending") -> dict:
    return {"status": status, "gate_type": "publish",
            "publish": {"target": rede, "source_id": source_id}}


@pytest.fixture
def evo(monkeypatch):
    """Injeta o dublê no lugar do `sdk_client.evo` que a ponte importa."""
    import types

    dublê = _Evo()
    modulo = types.ModuleType("sdk_client")
    modulo.evo = dublê
    monkeypatch.setitem(sys.modules, "sdk_client", modulo)
    return dublê


# ── idempotência ─────────────────────────────────────────────────────────

def test_reconhece_rede_ja_derivada(evo):
    evo.approvals = [_aprovacao("art1", "x"), _aprovacao("art1", "linkedin")]
    assert bridge.redes_ja_derivadas("art1") == {"x", "linkedin"}


def test_conta_derivacao_ja_decidida_tambem(evo):
    """Rejeitada continua sendo derivada.

    Reabrir o que o humano recusou é insistir num texto que ele leu e não
    quis — pior que não derivar.
    """
    evo.approvals = [_aprovacao("art1", "x", status="rejected"),
                     _aprovacao("art1", "threads", status="published")]
    assert bridge.redes_ja_derivadas("art1") == {"x", "threads"}


def test_nao_confunde_artigo_com_outro(evo):
    evo.approvals = [_aprovacao("outro", "x")]
    assert bridge.redes_ja_derivadas("art1") == set()


def test_gate_do_blog_nao_conta_como_derivacao(evo):
    """`publish_ref` é o artigo publicado pelo gate do blog, não um post de rede.

    Confundir os dois faria a aprovação do próprio artigo parecer uma derivação
    e as três redes seriam puladas para sempre.
    """
    evo.approvals = [{"status": "published", "gate_type": "publish",
                      "publish": {"target": "blog", "publish_ref": "art1"}}]
    assert bridge.redes_ja_derivadas("art1") == set()


def test_api_indisponivel_nao_bloqueia_derivacao(evo, monkeypatch):
    """Fail-open: aprovação repetida se rejeita, artigo não derivado some."""
    def explode(*a, **k):
        raise RuntimeError("api fora do ar")

    monkeypatch.setattr(evo, "get", explode)
    assert bridge.redes_ja_derivadas("art1") == set()


def test_distribuir_pula_rede_ja_derivada(evo, monkeypatch):
    evo.approvals = [_aprovacao("art1", "x")]
    monkeypatch.setattr(bridge, "buscar_post",
                        lambda _id: {"id": "art1", "title": "T", "status": "published",
                                     "url": "https://blog/x", "excerpt": "e"})
    monkeypatch.setattr(bridge, "adaptar", lambda post, rede: f"texto de {rede}")
    monkeypatch.setattr(bridge, "midia_do_post", lambda post: ([], ""))

    r = bridge.distribuir("art1")
    assert "x" in r["pulados"]
    assert set(r["redes"]) == {"linkedin", "threads"}


def test_rede_ja_derivada_nao_chama_o_modelo(evo, monkeypatch):
    """Pular depois de gerar custaria uma chamada de modelo por passada.

    O varredor roda a cada 15 minutos sobre a mesma janela — gerar para
    descartar seria a conta de geração multiplicada por 96 ao dia.
    """
    evo.approvals = [_aprovacao("art1", r) for r in bridge.REDES]
    monkeypatch.setattr(bridge, "buscar_post",
                        lambda _id: {"id": "art1", "title": "T", "status": "published",
                                     "url": "https://blog/x"})
    monkeypatch.setattr(bridge, "midia_do_post", lambda post: ([], ""))
    chamadas = []
    monkeypatch.setattr(bridge, "adaptar",
                        lambda post, rede: chamadas.append(rede) or "texto")

    bridge.distribuir("art1")
    assert chamadas == []


# ── o varredor ───────────────────────────────────────────────────────────

def test_janela_ignora_artigo_antigo(monkeypatch):
    monkeypatch.setattr(bridge.requests, "get", lambda *a, **k: _Resposta([
        {"id": "novo", "title": "A", "published_at": _agora(2)},
        {"id": "velho", "title": "B", "published_at": _agora(200)},
    ]))
    monkeypatch.setenv("GHOST_URL", "https://blog.x")
    monkeypatch.setenv("GHOST_ADMIN_API_KEY", "aa:bb")
    ids = [p["id"] for p in bridge.posts_publicados_recentes(26)]
    assert ids == ["novo"]


def test_data_ilegivel_nao_derruba_a_varredura(monkeypatch):
    monkeypatch.setattr(bridge.requests, "get", lambda *a, **k: _Resposta([
        {"id": "quebrado", "title": "A", "published_at": "ontem de tarde"},
        {"id": "bom", "title": "B", "published_at": _agora(1)},
    ]))
    monkeypatch.setenv("GHOST_URL", "https://blog.x")
    monkeypatch.setenv("GHOST_ADMIN_API_KEY", "aa:bb")
    assert [p["id"] for p in bridge.posts_publicados_recentes(26)] == ["bom"]


def test_sem_credencial_do_ghost_devolve_vazio(monkeypatch):
    monkeypatch.delenv("GHOST_URL", raising=False)
    monkeypatch.delenv("GHOST_ADMIN_API_KEY", raising=False)
    assert bridge.posts_publicados_recentes(26) == []


def test_varredor_deriva_o_artigo_orfao(evo, monkeypatch):
    """O caso de 27/07: publicado pelo Ghost, sem nenhuma rede."""
    monkeypatch.setattr(bridge, "posts_publicados_recentes",
                        lambda horas=26, limite=15: [
                            {"id": "orfao", "title": "Agendado", "published_at": _agora(1)}])
    derivados = []
    monkeypatch.setattr(bridge, "distribuir",
                        lambda pid, **kw: derivados.append(pid) or {"ok": True})

    r = bridge.derivar_pendentes()
    assert derivados == ["orfao"]
    assert r["artigos"][0]["acao"] == "derivado"
    assert set(r["artigos"][0]["faltando"]) == set(bridge.REDES)


def test_varredor_nao_repete_artigo_ja_derivado(evo, monkeypatch):
    evo.approvals = [_aprovacao("pronto", r) for r in bridge.REDES]
    monkeypatch.setattr(bridge, "posts_publicados_recentes",
                        lambda horas=26, limite=15: [
                            {"id": "pronto", "title": "Já foi", "published_at": _agora(1)}])
    monkeypatch.setattr(bridge, "distribuir",
                        lambda *a, **k: pytest.fail("não podia derivar de novo"))

    r = bridge.derivar_pendentes()
    assert r["artigos"][0]["acao"] == "nada a fazer"


def test_varredor_completa_derivacao_parcial(evo, monkeypatch):
    """Uma rede que falhou na primeira passada tem de ser retomada."""
    evo.approvals = [_aprovacao("meio", "x")]
    monkeypatch.setattr(bridge, "posts_publicados_recentes",
                        lambda horas=26, limite=15: [
                            {"id": "meio", "title": "Metade", "published_at": _agora(1)}])
    monkeypatch.setattr(bridge, "distribuir", lambda pid, **kw: {"ok": True})

    r = bridge.derivar_pendentes()
    assert set(r["artigos"][0]["faltando"]) == {"linkedin", "threads"}
    assert r["artigos"][0]["acao"] == "derivado"


def test_dry_run_nao_deriva(evo, monkeypatch):
    monkeypatch.setattr(bridge, "posts_publicados_recentes",
                        lambda horas=26, limite=15: [
                            {"id": "orfao", "title": "A", "published_at": _agora(1)}])
    monkeypatch.setattr(bridge, "distribuir",
                        lambda *a, **k: pytest.fail("dry-run não pode derivar"))

    assert bridge.derivar_pendentes(dry_run=True)["artigos"][0]["acao"] == "derivaria (dry-run)"


# ── o que liga o varredor ao agendamento ─────────────────────────────────

def test_gate_do_blog_nao_deriva_agendado():
    """Agendado não pode derivar na aprovação: o post ainda não está publicado.

    `distribuir` recusa post fora de `published`, então derivar ali produziria
    um "ignorado" silencioso e a falsa sensação de que foi tratado.
    """
    fonte = (REPO_ROOT / "dashboard" / "backend" / "heartbeat_outcome.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def _run_blog_publish")[1].split("def _derivar_redes")[0]
    assert 'resultado.get("status") != "scheduled"' in trecho
    assert "derivar_redes_pendentes" in trecho, \
        "o comentário precisa apontar quem cobre o agendado"


def test_rotina_existe_onde_o_scheduler_procura():
    assert (REPO_ROOT / "ADWs" / "routines" / "derivar_redes_pendentes.py").is_file()


def test_varredor_esta_agendado():
    fonte = (REPO_ROOT / "scheduler.py").read_text(encoding="utf-8")
    assert "derivar_redes_pendentes.py" in fonte, \
        "sem entrada no scheduler o varredor nunca roda"


def test_api_expoe_source_id():
    """Sem `source_id` no preview, `redes_ja_derivadas` não reconhece nada."""
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def _render_publish_preview")[1].split("\ndef ")[0]
    assert '"source_id"' in trecho


class _Resposta:
    def __init__(self, posts):
        self.status_code = 200
        self._posts = posts

    def json(self):
        return {"posts": self._posts}
