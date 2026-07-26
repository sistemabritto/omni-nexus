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


def test_as_redes_do_blog_levam_a_capa(post_publicado):
    """Invertido em 2026-07-26. A regra anterior mandava imagem só para o
    Instagram, com o argumento de que nas outras a capa competiria com o
    preview do link. Como o Instagram saiu deste gatilho, na prática todo post
    saía sem imagem nenhuma — e o argumento não vale para as três que ficaram:
    no LinkedIn o link vai no primeiro comentário e no Threads não vai link,
    então não existe preview para competir.
    """
    r = bridge.distribuir("p1", dry_run=True)
    for rede in bridge.REDES:
        assert r["redes"][rede]["midia"] == [post_publicado["feature_image"]]


def test_artigo_sem_capa_nao_atrapalha_a_distribuicao(monkeypatch, post_publicado):
    """Sem capa as três redes seguem normalmente — post sem imagem é pior que
    post com imagem, mas melhor que post nenhum."""
    monkeypatch.setattr(bridge, "buscar_post", lambda _: {**post_publicado, "feature_image": ""})
    r = bridge.distribuir("p1", dry_run=True)
    assert set(r["redes"]) == set(bridge.REDES)
    assert r["pulados"] == {}


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


# ── a aprovação precisa de ticket (validação real, 2026-07-25) ───────────

@pytest.fixture
def api_falsa(monkeypatch):
    """Captura as chamadas de API sem rede, com o contrato real do endpoint."""
    chamadas = {"tickets": [], "approvals": []}

    class _Evo:
        @staticmethod
        def post(rota, corpo):
            if rota == "/api/tickets":
                chamadas["tickets"].append(corpo)
                return {"id": f"tkt-{len(chamadas['tickets'])}"}
            if rota == "/api/approvals":
                # É exatamente isto que a API exige — sem ticket_id, 400.
                if not corpo.get("ticket_id"):
                    raise RuntimeError("400: ticket_id is required for gate_type=publish")
                chamadas["approvals"].append(corpo)
                return {"id": len(chamadas["approvals"]), "status": "pending"}
            raise AssertionError(f"rota inesperada: {rota}")

    import sys as _sys
    import types as _types

    fake = _types.ModuleType("sdk_client")
    fake.evo = _Evo()
    monkeypatch.setitem(_sys.modules, "sdk_client", fake)
    return chamadas


def test_cada_rede_abre_aprovacao_ancorada_num_ticket(post_publicado, api_falsa):
    """Sem ticket_id a API devolve 400 e a aprovação nunca chega ao Telegram —
    o trabalho todo morre no último passo, em silêncio."""
    r = bridge.distribuir("p1")
    assert r["ok"] is True, f"alguma rede falhou: {r['redes']}"
    assert len(api_falsa["approvals"]) == len(bridge.REDES)
    for chamada in api_falsa["approvals"]:
        assert chamada["ticket_id"], "aprovação sem ticket é recusada pela API"
        assert chamada["gate_type"] == "publish"


def test_um_ticket_por_rede_e_nao_um_agregado(post_publicado, api_falsa):
    """Aprovação agregada faria o humano aprovar um resumo — o problema de
    confiança que o gate existe para evitar."""
    bridge.distribuir("p1")
    assert len(api_falsa["tickets"]) == len(bridge.REDES)
    titulos = {t["title"] for t in api_falsa["tickets"]}
    assert len(titulos) == len(bridge.REDES), "cada rede precisa do seu próprio ticket"


def test_ticket_carrega_o_link_do_artigo(post_publicado, api_falsa):
    bridge.distribuir("p1")
    for t in api_falsa["tickets"]:
        assert "blog.sistemabritto.com.br" in (t.get("description") or "")
        assert t["assignee_agent"] == "pixel-social-media"


def test_outcome_da_aprovacao_leva_o_link_para_o_card(post_publicado, api_falsa):
    bridge.distribuir("p1")
    for a in api_falsa["approvals"]:
        assert a["payload"]["outcome"]["source_url"].startswith("http")


# ── roteamento e horário (correções do Felipe, 25/07) ────────────────────

def test_artigo_do_blog_nao_vai_para_instagram():
    """No Instagram o link não é clicável no feed: republicar artigo lá vira
    post que não converte e ocupa o espaço do conteúdo visual nativo."""
    assert "instagram" not in bridge.REDES
    assert set(bridge.REDES) == {"x", "linkedin", "threads"}


def test_suporte_a_instagram_continua_existindo_no_gate():
    """Tirar do blog não é remover a capacidade — conteúdo que nasce visual
    ainda publica lá."""
    assert "instagram" in bridge.LIMITES
    assert ho._publish_settings_for("instagram", "t", provider="instagram-standalone")


def test_threads_nao_leva_link_no_texto(post_publicado, api_falsa):
    """Post recompensa: o link sai do texto e vira comentário com palavra-chave.
    A rede pune link no corpo, e cada comentário é um lead identificado."""
    r = bridge.distribuir("p1", dry_run=True)
    texto = r["redes"]["threads"]["preview"]
    assert "http" not in texto, f"link vazou no Threads: {texto!r}"
    assert "coment" in texto.lower(), "faltou o CTA de comentário"


def test_x_continua_levando_o_link(post_publicado, api_falsa):
    assert "http" in bridge.distribuir("p1", dry_run=True)["redes"]["x"]["preview"]


# ── janelas de horário ───────────────────────────────────────────────────

def _brt(dt):
    return dt.astimezone(bridge._zona())


def test_madrugada_e_empurrada_para_a_manha():
    """Artigo publicado às 23h caía às 1h — post morre sem ser visto."""
    from datetime import datetime, timezone as _tz

    madrugada = datetime(2026, 7, 26, 4, 0, tzinfo=_tz.utc)  # 01:00 BRT
    assert _brt(bridge.proximo_horario("x", madrugada)).hour == 8


def test_horario_dentro_da_janela_pega_a_proxima_do_dia():
    from datetime import datetime, timezone as _tz

    # 13:00 BRT — passou das 12h, próxima janela do X é 18h
    assert _brt(bridge.proximo_horario("x", datetime(2026, 7, 26, 16, 0, tzinfo=_tz.utc))).hour == 18


def test_depois_da_ultima_janela_vai_para_o_dia_seguinte():
    from datetime import datetime, timezone as _tz

    tarde = datetime(2026, 7, 26, 23, 30, tzinfo=_tz.utc)  # 20:30 BRT
    resultado = _brt(bridge.proximo_horario("linkedin", tarde))
    assert resultado.hour == 8 and resultado.day == 27


def test_nunca_agenda_para_tras():
    """Postiz recusa data no passado e o gate é fail-closed — uma aprovação que
    morre na hora de publicar é pior que nenhuma."""
    from datetime import datetime, timezone as _tz

    for hora in range(24):
        agora = datetime(2026, 7, 26, hora, 17, tzinfo=_tz.utc)
        for rede in bridge.REDES:
            assert bridge.proximo_horario(rede, agora) >= agora


def test_threads_tem_janela_mais_noturna_que_linkedin():
    assert min(bridge.JANELAS["threads"]) > min(bridge.JANELAS["linkedin"])


def test_rede_sem_janela_nao_quebra():
    from datetime import datetime, timezone as _tz

    agora = datetime(2026, 7, 26, 5, 0, tzinfo=_tz.utc)
    assert bridge.proximo_horario("discord", agora) == agora
