"""
tests/goals/test_instagram_via_postiz.py

Instagram no fluxo (2026-07-25) — a rede ficava de fora por dois motivos, e
nenhum deles era "falta credencial":

1. `select_integration("instagram")` casava só com `identifier == "instagram"`.
   A conta do Felipe é `instagram-standalone` (login pelo Instagram, sem página
   do Facebook), então o gate respondia "nenhuma integração ativa e inequívoca"
   com a integração conectada e funcionando na frente dele.

2. A ponte Ghost -> redes pulava o Instagram sempre, porque nunca montava
   mídia. O Postiz recusa Instagram sem imagem — é regra da plataforma —, mas a
   imagem existia o tempo todo: é a capa do artigo (`feature_image`).

O detalhe que amarra os dois: o `__type` do settings tem que ser o provider
REAL da integração. Resolver `instagram-standalone` e mandar `__type:
"instagram"` troca uma falha explícita por uma recusa do Postiz na hora de
publicar — depois do humano ter aprovado.

Run:
    pytest tests/goals/test_instagram_via_postiz.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_social_bridge as bridge  # noqa: E402
import heartbeat_outcome as ho  # noqa: E402
import postiz_client as pc  # noqa: E402


def _client(**kw) -> pc.PostizClient:
    base = {"base_url": "https://postiz.example.com", "api_key": "k"}
    base.update(kw)
    return pc.PostizClient(**base)


def _integ(identifier: str, id_: str = "i1", disabled: bool = False) -> dict:
    return {"id": id_, "identifier": identifier, "name": identifier, "disabled": disabled}


# ── resolução da integração ──────────────────────────────────────────────

def test_instagram_resolve_a_conta_standalone():
    """O caso real: a única conta conectada é `instagram-standalone`."""
    achado = _client().select_integration("instagram", [_integ("instagram-standalone", "ig1")])
    assert achado is not None and achado["id"] == "ig1"


def test_provider_canonico_vence_a_variante():
    achado = _client().select_integration(
        "instagram", [_integ("instagram-standalone", "ig-sa"), _integ("instagram", "ig-fb")])
    assert achado["id"] == "ig-fb"


def test_duas_contas_do_mesmo_provider_continuam_ambiguas():
    """Alias não afrouxa o critério: empate real ainda exige POSTIZ_INTEGRATION_*_ID."""
    achado = _client().select_integration(
        "instagram", [_integ("instagram-standalone", "a"), _integ("instagram-standalone", "b")])
    assert achado is None


def test_id_fixado_no_env_resolve_a_ambiguidade():
    cli = _client(integration_ids={"instagram": "b"})
    achado = cli.select_integration(
        "instagram", [_integ("instagram-standalone", "a"), _integ("instagram-standalone", "b")])
    assert achado["id"] == "b"


def test_conta_desabilitada_nao_conta():
    assert _client().select_integration(
        "instagram", [_integ("instagram-standalone", "x", disabled=True)]) is None


def test_linkedin_page_tambem_resolve():
    achado = _client().select_integration("linkedin", [_integ("linkedin-page", "lp")])
    assert achado["id"] == "lp"


def test_plataforma_sem_alias_continua_exigindo_nome_exato():
    assert _client().select_integration("x", [_integ("threads")]) is None
    assert _client().select_integration("x", [_integ("x", "x1")])["id"] == "x1"


# ── o __type tem que casar com o provider resolvido ──────────────────────

def test_settings_do_instagram_seguem_o_provider_resolvido():
    s = ho._publish_settings_for("instagram", "texto", provider="instagram-standalone")
    assert s["__type"] == "instagram-standalone"
    assert s["post_type"] == "post"


def test_settings_do_instagram_canonico():
    assert ho._publish_settings_for("instagram", "t", provider="instagram")["__type"] == "instagram"


def test_settings_do_linkedin_page():
    assert ho._publish_settings_for("linkedin", "t", provider="linkedin-page")["__type"] == "linkedin-page"
    assert ho._publish_settings_for("linkedin", "t", provider="linkedin")["__type"] == "linkedin"


def test_sem_provider_cai_no_target_como_antes():
    """Compatibilidade: chamadas antigas sem `provider` não podem mudar de comportamento."""
    assert ho._publish_settings_for("threads", "t")["__type"] == "threads"
    assert ho._publish_settings_for("discord", "t")["__type"] == "discord"


# ── mídia do artigo ──────────────────────────────────────────────────────

class _ClienteFake:
    def __init__(self, hosts):
        self.hosts = hosts

    def is_safe_media_url(self, url):
        return any(h in url for h in self.hosts)


@pytest.fixture
def postiz_permissivo(monkeypatch):
    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: _ClienteFake(["blog.sistemabritto.com.br"])))


def test_capa_do_artigo_vira_midia(postiz_permissivo):
    url = "https://blog.sistemabritto.com.br/content/images/2026/06/capa.png"
    midia, motivo = bridge.midia_do_post({"feature_image": url})
    assert midia == [url] and motivo == ""


def test_artigo_sem_capa_explica_o_motivo(postiz_permissivo):
    midia, motivo = bridge.midia_do_post({"feature_image": None})
    assert midia == [] and "feature_image" in motivo


def test_capa_em_host_nao_permitido_explica_o_que_fazer(postiz_permissivo):
    midia, motivo = bridge.midia_do_post({"feature_image": "https://cdn.aleatorio.com/x.png"})
    assert midia == []
    assert "POSTIZ_ALLOWED_MEDIA_HOSTS" in motivo, "o motivo tem que dizer a ação, não só o erro"


def test_sem_postiz_configurado_nao_afirma_que_a_url_e_segura(monkeypatch):
    monkeypatch.setattr(pc.PostizClient, "from_env", classmethod(lambda cls: None))
    midia, motivo = bridge.midia_do_post({"feature_image": "https://blog.sistemabritto.com.br/a.png"})
    assert midia == [] and "POSTIZ_URL" in motivo


# ── a ponte, ponta a ponta (dry run) ─────────────────────────────────────

@pytest.fixture
def post_publicado(monkeypatch, postiz_permissivo):
    post = {
        "id": "p1", "status": "published", "title": "IA open source vale a pena?",
        "custom_excerpt": "O que muda para quem vende.",
        "url": "https://blog.sistemabritto.com.br/ia-open-source/",
        "plaintext": "Corpo do artigo.",
        "feature_image": "https://blog.sistemabritto.com.br/content/images/capa.png",
    }
    monkeypatch.setattr(bridge, "buscar_post", lambda _: post)
    monkeypatch.setenv("XAI_API_KEY", "")  # força o fallback, sem chamada de rede
    return post


def test_instagram_entra_no_fluxo_quando_ha_capa(post_publicado):
    r = bridge.distribuir("p1", dry_run=True)
    assert "instagram" in r["redes"], f"Instagram ficou de fora: {r['pulados']}"
    assert r["redes"]["instagram"]["midia"] == [post_publicado["feature_image"]]


def test_as_outras_redes_nao_levam_a_capa(post_publicado):
    """No X/LinkedIn/Threads a imagem competiria com o preview do link."""
    r = bridge.distribuir("p1", dry_run=True)
    for rede in ("x", "linkedin", "threads"):
        assert r["redes"][rede]["midia"] == []


def test_sem_capa_o_instagram_sai_com_motivo_legivel(monkeypatch, post_publicado):
    monkeypatch.setattr(bridge, "buscar_post", lambda _: {**post_publicado, "feature_image": ""})
    r = bridge.distribuir("p1", dry_run=True)
    assert "instagram" not in r["redes"]
    assert "feature_image" in r["pulados"]["instagram"]
    assert set(r["redes"]) == {"x", "linkedin", "threads"}, "as outras redes seguem normalmente"


# ── Cloudflare 1010 ──────────────────────────────────────────────────────

def test_ghost_e_chamado_com_user_agent_de_navegador(monkeypatch):
    """Sem UA de navegador o Cloudflare devolve 403/1010 e o erro parece
    credencial inválida — foi o que fez trocar chave que estava certa."""
    capturado = {}

    def fake_get(url, headers=None, timeout=None):
        capturado.update(headers or {})

        class R:
            status_code = 200

            @staticmethod
            def json():
                return {"posts": [{"id": "p1"}]}
        return R()

    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    monkeypatch.setenv("GHOST_ADMIN_API_KEY", "abc:" + "ab" * 16)
    monkeypatch.setattr(bridge.requests, "get", fake_get)

    bridge.buscar_post("p1")
    assert "Mozilla/" in capturado.get("User-Agent", ""), "UA de biblioteca é bloqueado pelo Cloudflare"
    assert capturado["Authorization"].startswith("Ghost ")
