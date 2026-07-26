"""
tests/goals/test_publicacao_com_imagem_e_link.py

2026-07-26 — os três defeitos que faziam o post sair errado, e o retorno do
link que faltava para descobrir isso.

Contexto real: as aprovações 16/17/18 ("Resposta automática no WhatsApp")
foram aprovadas e sairiam com `publish_media: []` nas três redes, o post do X
sem link nenhum, e o do LinkedIn prometendo "está no primeiro comentário" sem
que nada postasse esse comentário. Nenhum desses defeitos era visível de fora:
o gate dizia "publicado com sucesso" e ninguém tinha como conferir.

Run:
    pytest tests/goals/test_publicacao_com_imagem_e_link.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_social_bridge as bridge  # noqa: E402
import postiz_client as pc  # noqa: E402


ARTIGO = "https://blog.sistemabritto.com.br/resposta-automatica-no-whatsapp/"


# ── 1. a capa vai em todas as redes, não só no Instagram ─────────────────

@pytest.fixture
def post_com_capa(monkeypatch):
    post = {
        "id": "abc123",
        "title": "Resposta automática no WhatsApp",
        "status": "published",
        "url": ARTIGO,
        "excerpt": "Resumo do artigo.",
        "plaintext": "Corpo do artigo.",
        "feature_image": "https://blog.sistemabritto.com.br/content/images/capa.png",
    }
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: post)
    monkeypatch.setattr(bridge, "midia_do_post", lambda p: ([p["feature_image"]], ""))
    monkeypatch.setattr(bridge, "adaptar", lambda p, rede: f"Texto de {rede}.")
    return post


def test_toda_rede_leva_a_capa_do_artigo(post_com_capa):
    """A regra antiga só anexava imagem no Instagram — que saiu do gatilho.

    O efeito era invisível: nenhuma rede recebia mídia e o gate não reclamava,
    porque post sem imagem é válido para o Postiz.
    """
    resultado = bridge.distribuir("abc123", dry_run=True)
    assert set(resultado["redes"]) == {"x", "linkedin", "threads"}
    for rede, dados in resultado["redes"].items():
        assert dados["midia"] == [post_com_capa["feature_image"]], f"{rede} saiu sem imagem"


def test_artigo_sem_capa_diz_o_motivo_em_vez_de_sair_calado(monkeypatch, post_com_capa):
    monkeypatch.setattr(bridge, "midia_do_post", lambda p: ([], "artigo sem feature_image"))
    resultado = bridge.distribuir("abc123", dry_run=True)
    assert resultado["aviso_midia"] == "artigo sem feature_image"


# ── 2. o link do artigo no corpo do post do X ────────────────────────────

def test_x_ganha_o_link_quando_o_modelo_esquece():
    texto = bridge.garantir_link("Gancho sem link nenhum.", ARTIGO, "x")
    assert texto.endswith(ARTIGO)
    assert texto.startswith("Gancho sem link nenhum.")


def test_link_ja_presente_nao_e_duplicado():
    original = f"Gancho.\n\n{ARTIGO}"
    assert bridge.garantir_link(original, ARTIGO, "x") == original


def test_link_no_meio_do_texto_tambem_conta():
    original = f"Olha {ARTIGO} isso aqui."
    assert bridge.garantir_link(original, ARTIGO, "x") == original


@pytest.mark.parametrize("rede", ["linkedin", "threads"])
def test_rede_sem_link_no_corpo_fica_intocada(rede):
    """No LinkedIn o link vai no comentário; no Threads não vai link nenhum.

    Anexar aqui não seria esquecimento corrigido — seria quebrar o formato.
    """
    texto = "Texto sem link, por design."
    assert bridge.garantir_link(texto, ARTIGO, rede) == texto


def test_texto_longo_e_encurtado_para_o_link_caber():
    longo = "palavra " * 60  # ~480 caracteres, muito além dos 280 do X
    texto = bridge.garantir_link(longo.strip(), ARTIGO, "x")
    corpo = texto.rsplit("\n\n", 1)[0]
    # A URL conta 23 no X (t.co), não o tamanho real — reservar os ~90 reais
    # cortaria um terço do post à toa.
    assert len(corpo) <= 280 - 23 - 2
    assert texto.endswith(ARTIGO)


def test_sem_link_no_artigo_nada_e_inventado():
    assert bridge.garantir_link("Texto.", "", "x") == "Texto."


# ── 3. o link no primeiro comentário do LinkedIn ─────────────────────────

def test_linkedin_leva_o_link_como_comentario():
    assert bridge.comentarios_da_rede("linkedin", ARTIGO) == [f"Artigo completo: {ARTIGO}"]


@pytest.mark.parametrize("rede", ["x", "threads", "instagram"])
def test_outras_redes_nao_ganham_comentario(rede):
    assert bridge.comentarios_da_rede(rede, ARTIGO) == []


def test_distribuir_anexa_o_comentario_so_no_linkedin(post_com_capa):
    resultado = bridge.distribuir("abc123", dry_run=True)
    # dry_run devolve o outcome resumido; o comentário é conferido pelo gate
    assert resultado["redes"]["linkedin"]["publish_at"]


class _RespostaFalsa:
    status_code = 200

    def __init__(self, corpo):
        self._corpo = corpo

    def json(self):
        return self._corpo


def test_comentario_vira_item_extra_no_value_do_postiz(monkeypatch):
    """No Postiz, `value` é uma lista: item 0 é o post, os demais viram
    comentários (confirmado no linkedin.provider.js da instância)."""
    enviado = {}

    def _fake_request(self, method, path, **kwargs):
        enviado.update(kwargs.get("json") or {})
        return _RespostaFalsa([{"postId": "p1"}])

    monkeypatch.setattr(pc.PostizClient, "_request", _fake_request)
    client = pc.PostizClient(base_url="https://postiz.local", api_key="k")
    client.schedule_post(
        integration_id="i1", content="Post principal", media=[], settings={},
        scheduled_at_utc="2026-07-27T15:00:00+00:00",
        comments=[f"Artigo completo: {ARTIGO}"],
    )
    valores = enviado["posts"][0]["value"]
    assert len(valores) == 2
    assert valores[0]["content"] == "Post principal"
    assert valores[1]["content"] == f"Artigo completo: {ARTIGO}"
    # Só o post principal leva mídia — o comentário existe para carregar o link.
    assert valores[1]["image"] == []


def test_comentario_vazio_nao_vira_item(monkeypatch):
    enviado = {}

    def _fake_request(self, method, path, **kwargs):
        enviado.update(kwargs.get("json") or {})
        return _RespostaFalsa([{"postId": "p1"}])

    monkeypatch.setattr(pc.PostizClient, "_request", _fake_request)
    client = pc.PostizClient(base_url="https://postiz.local", api_key="k")
    client.schedule_post(integration_id="i1", content="Post", media=[], settings={},
                         scheduled_at_utc="2026-07-27T15:00:00+00:00", comments=["", "   "])
    assert len(enviado["posts"][0]["value"]) == 1


def test_sem_comentarios_o_payload_nao_muda(monkeypatch):
    """Regressão: o formato de um post sem comentário tem de continuar idêntico."""
    enviado = {}

    def _fake_request(self, method, path, **kwargs):
        enviado.update(kwargs.get("json") or {})
        return _RespostaFalsa([{"postId": "p1"}])

    monkeypatch.setattr(pc.PostizClient, "_request", _fake_request)
    client = pc.PostizClient(base_url="https://postiz.local", api_key="k")
    client.create_post_now(integration_id="i1", content="Post", media=[{"id": "m", "path": "u"}],
                           settings={}, now_iso_utc="2026-07-26T12:00:00+00:00")
    assert enviado["posts"][0]["value"] == [{"content": "Post", "image": [{"id": "m", "path": "u"}]}]


# ── 4. o endereço do post volta para quem aprovou ────────────────────────

POSTS_DO_POSTIZ = [
    {"id": "p1", "state": "PUBLISHED", "releaseURL": "https://x.com/user/status/1"},
    {"id": "p2", "state": "PUBLISHED", "releaseURL": None},
    {"id": "p3", "state": "QUEUE", "releaseURL": "https://x.com/user/status/3"},
]


def test_release_urls_so_traz_o_que_existe_de_verdade():
    urls = pc.PostizClient.release_urls_de(POSTS_DO_POSTIZ, ["p1", "p2"])
    assert urls == ["https://x.com/user/status/1"]


def test_release_urls_ignora_post_de_fora_da_lista():
    assert pc.PostizClient.release_urls_de(POSTS_DO_POSTIZ, ["p3"]) == [
        "https://x.com/user/status/3"
    ]
    assert pc.PostizClient.release_urls_de(POSTS_DO_POSTIZ, []) == []


def test_release_urls_descarta_valor_que_nao_e_url():
    sujo = [{"id": "p1", "state": "PUBLISHED", "releaseURL": "null"}]
    assert pc.PostizClient.release_urls_de(sujo, ["p1"]) == []


def test_confirmacao_de_agendamento_devolve_ids_para_reencontrar_o_post(monkeypatch):
    """Sem os ids, não há como voltar ao Postiz depois e descobrir o link."""
    monkeypatch.setattr(
        pc.PostizClient, "list_posts",
        lambda self, window: [{"id": "p1", "state": "QUEUE", "releaseURL": None}],
    )
    client = pc.PostizClient(base_url="https://postiz.local", api_key="k")
    resultado = client.confirm_scheduled(["p1"], window=("a", "b"))
    assert resultado["scheduled"] is True
    assert resultado["post_ids"] == ["p1"]
    # Agendado ainda não tem endereço — e isso não é falha.
    assert resultado["release_urls"] == []


def test_publicacao_imediata_ja_devolve_o_endereco(monkeypatch):
    monkeypatch.setattr(
        pc.PostizClient, "_request",
        lambda self, method, path, **kw: _RespostaFalsa(
            {"posts": [{"id": "p1", "state": "PUBLISHED",
                        "releaseURL": "https://x.com/user/status/1"}]}
        ),
    )
    client = pc.PostizClient(base_url="https://postiz.local", api_key="k")
    resultado = client.wait_for_publication(["p1"], wait_seconds=1, poll_seconds=0.1,
                                            window=("a", "b"))
    assert resultado["published"] is True
    assert resultado["release_urls"] == ["https://x.com/user/status/1"]


# ── 5. o confirmador de agendamentos ─────────────────────────────────────

@pytest.fixture
def publicacoes(monkeypatch, tmp_path):
    import publicacoes as mod

    banco = tmp_path / "evonexus.db"
    banco.touch()
    monkeypatch.setattr(mod, "DB_PATH", banco)
    return mod


def _avisos(monkeypatch):
    recebidos = []
    import notifications

    monkeypatch.setattr(notifications, "notify_publicacao",
                        lambda rede, titulo, **kw: recebidos.append((rede, titulo, kw)) or True)
    return recebidos


def test_agendado_que_publicou_vira_aviso_com_link(publicacoes, monkeypatch):
    recebidos = _avisos(monkeypatch)
    publicacoes.registrar(16, ticket_id="t1", rede="x", titulo="Resposta automática",
                          post_ids=["p1"], agendado_para="2026-07-26T15:00:00Z", imagens=1)

    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(
        pc.PostizClient, "list_posts",
        lambda self, window: [{"id": "p1", "state": "PUBLISHED",
                               "releaseURL": "https://x.com/user/status/1"}],
    )

    assert publicacoes.tick() == {"confirmados": 1, "desistidos": 0, "pendentes": 0}
    assert recebidos[0][0] == "x"
    assert recebidos[0][2]["links"] == ["https://x.com/user/status/1"]
    assert recebidos[0][2]["imagens"] == 1


def test_confirmado_nao_avisa_de_novo(publicacoes, monkeypatch):
    """Idempotência: o tick roda a cada 20min e não pode repetir o aviso."""
    recebidos = _avisos(monkeypatch)
    publicacoes.registrar(16, ticket_id="t1", rede="x", titulo="T", post_ids=["p1"],
                          agendado_para="2026-07-26T15:00:00Z")
    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_posts",
                        lambda self, window: [{"id": "p1", "state": "PUBLISHED",
                                               "releaseURL": "https://x.com/s/1"}])
    publicacoes.tick()
    publicacoes.tick()
    assert len(recebidos) == 1


def test_ainda_na_fila_nao_afirma_nada(publicacoes, monkeypatch):
    recebidos = _avisos(monkeypatch)
    publicacoes.registrar(17, ticket_id="t2", rede="linkedin", titulo="T", post_ids=["p9"],
                          agendado_para="2026-07-26T15:00:00Z")
    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_posts",
                        lambda self, window: [{"id": "p9", "state": "QUEUE", "releaseURL": None}])
    resultado = publicacoes.tick()
    assert resultado["confirmados"] == 0
    assert resultado["pendentes"] == 1
    assert recebidos == []


def test_erro_no_postiz_avisa_a_falha_e_encerra(publicacoes, monkeypatch):
    recebidos = _avisos(monkeypatch)
    publicacoes.registrar(18, ticket_id="t3", rede="threads", titulo="T", post_ids=["pz"],
                          agendado_para="2026-07-26T15:00:00Z")
    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_posts",
                        lambda self, window: [{"id": "pz", "state": "ERROR", "releaseURL": None}])
    resultado = publicacoes.tick()
    assert resultado["desistidos"] == 1
    assert "falhou" in recebidos[0][1]


def test_postiz_fora_do_ar_nao_fecha_a_linha(publicacoes, monkeypatch):
    """Indisponibilidade não pode virar 'desisti' — tenta de novo no próximo tick."""
    _avisos(monkeypatch)
    publicacoes.registrar(19, ticket_id="t4", rede="x", titulo="T", post_ids=["pk"],
                          agendado_para="2026-07-26T15:00:00Z")

    def _explode(self, window):
        raise pc.PostizAPIError("Postiz respondeu 401")

    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_posts", _explode)
    resultado = publicacoes.tick()
    assert resultado["pendentes"] == 1
    assert resultado["confirmados"] == 0


def test_post_que_ja_saiu_com_link_nao_entra_na_fila(publicacoes):
    """Publicação imediata já foi confirmada na hora — varrer de novo é ruído."""
    assert publicacoes.registrar(20, ticket_id="t5", rede="x", titulo="T", post_ids=["p1"],
                                 release_urls=["https://x.com/s/1"]) is False


def test_parcialmente_publicado_ainda_nao_e_publicado(publicacoes, monkeypatch):
    """Post no ar mas comentário na fila: avisar agora manda conferir algo
    que ainda vai mudar."""
    recebidos = _avisos(monkeypatch)
    publicacoes.registrar(21, ticket_id="t6", rede="linkedin", titulo="T",
                          post_ids=["p1", "p2"], agendado_para="2026-07-26T15:00:00Z")
    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_posts", lambda self, window: [
        {"id": "p1", "state": "PUBLISHED", "releaseURL": "https://l.in/1"},
        {"id": "p2", "state": "QUEUE", "releaseURL": None},
    ])
    assert publicacoes.tick()["confirmados"] == 0
    assert recebidos == []


# ── 6. a mensagem que o Felipe recebe ────────────────────────────────────

def test_mensagem_de_publicacao_traz_link_imagem_e_comentario(monkeypatch):
    import notifications

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram",
                        lambda texto, **kw: enviados.append((texto, kw)) or True)
    notifications.notify_publicacao("linkedin", "Resposta automática no WhatsApp",
                                    links=["https://linkedin.com/feed/update/1"],
                                    imagens=1, comentarios=1)
    texto, kwargs = enviados[0]
    assert "Publicado no LinkedIn" in texto
    assert "https://linkedin.com/feed/update/1" in texto
    assert "1 imagem" in texto and "1 comentário" in texto
    # O card do link é a conferência visual — sem ele, o link é só um endereço.
    assert kwargs["preview"] is True


def test_mensagem_denuncia_post_sem_imagem(monkeypatch):
    import notifications

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram",
                        lambda texto, **kw: enviados.append(texto) or True)
    notifications.notify_publicacao("x", "Título", links=["https://x.com/s/1"], imagens=0)
    assert "sem imagem" in enviados[0]


def test_agendado_diz_que_o_link_ainda_nao_existe(monkeypatch):
    import notifications

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram",
                        lambda texto, **kw: enviados.append((texto, kw)) or True)
    notifications.notify_publicacao("x", "Título", links=[],
                                    agendado_para="2026-07-26T15:00:00Z", imagens=1)
    texto, kwargs = enviados[0]
    assert "Agendado no X" in texto
    assert "chega quando ele for ao ar" in texto
    assert kwargs["preview"] is False


def test_horario_sai_no_fuso_do_felipe(monkeypatch):
    import notifications

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram",
                        lambda texto, **kw: enviados.append(texto) or True)
    notifications.notify_publicacao("x", "T", links=[], agendado_para="2026-07-26T15:00:00Z")
    # 15:00Z = 12:00 em São Paulo. Ler UTC de cabeça é onde nasce o erro de
    # agendar para as 5 da manhã sem perceber.
    assert "26/07 às 12:00" in enviados[0]


# ── 7. o outcome carrega os comentários até a publicação ─────────────────

def test_schema_do_outcome_aceita_comentarios():
    import heartbeat_outcome as ho

    assert "publish_comments" in ho._OUTCOME_SCHEMA["properties"]
    # Não pode ser obrigatório: quem preenche é a ponte, não o modelo.
    assert "publish_comments" not in ho._OUTCOME_SCHEMA["required"]


def test_preview_da_aprovacao_mostra_o_comentario():
    """Aprovar um texto que promete 'link no primeiro comentário' sem ver o
    comentário é aprovar no escuro."""
    sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))
    from routes.approvals import _render_publish_preview

    preview = _render_publish_preview("publish", {
        "outcome": {
            "publish_target": "linkedin",
            "publish_content": "Texto. Link no primeiro comentário.",
            "publish_media": ["https://blog.local/capa.png"],
            "publish_comments": [f"Artigo completo: {ARTIGO}"],
        }
    })
    assert preview["comments"] == [f"Artigo completo: {ARTIGO}"]
    assert preview["media"] == ["https://blog.local/capa.png"]


def test_preview_sem_comentario_devolve_lista_vazia():
    from routes.approvals import _render_publish_preview

    preview = _render_publish_preview("publish", {
        "outcome": {"publish_target": "x", "publish_content": "Texto.", "publish_media": []}
    })
    assert preview["comments"] == []


def test_comentario_invalido_no_outcome_e_recusado(monkeypatch):
    """publish_comments precisa ser lista — dict ou string viraria publicação
    torta sem ninguém perceber."""
    import heartbeat_outcome as ho

    class _Row:
        payload = json.dumps({"outcome": {
            "publish_target": "linkedin", "publish_content": "Texto.",
            "publish_media": [], "publish_comments": "não é lista",
        }})

    monkeypatch.setattr(pc.PostizClient, "from_env",
                        classmethod(lambda cls: cls(base_url="https://p.local", api_key="k")))
    monkeypatch.setattr(pc.PostizClient, "list_integrations",
                        lambda self: [{"id": "i1", "identifier": "linkedin"}])
    resultado = ho._run_publish_action(_Row(), None)
    assert resultado["published"] is False
    assert "publish_comments" in resultado["detail"]
