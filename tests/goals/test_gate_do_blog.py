"""
tests/goals/test_gate_do_blog.py

Fluxo de conteúdo em dois estágios (decisão do Felipe, 25/07/2026):

    draft no Ghost
      -> gate 1: humano lê o texto, confere os CTAs e vê a capa
      -> aprovado: publica/agenda no Ghost
      -> webhook post.published dispara a ponte
      -> gate 2..4: uma aprovação por rede (X, LinkedIn, Threads)

O ponto é a ordem. Derivar post de rede a partir de artigo não aprovado gasta
aprovação humana em cima de conteúdo que talvez nem devesse existir, e pior:
deixa o post da rede sair sem que ninguém tenha lido o artigo.

O erro perigoso deste módulo é confundir os dois textos: `publish_content` é o
resumo que o humano lê para decidir; o que se publica é o ARTIGO identificado
por `publish_ref`. Trocar um pelo outro publicaria o resumo como se fosse o
artigo.

Run:
    pytest tests/goals/test_gate_do_blog.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import ghost_publisher as gp  # noqa: E402
import ghost_social_bridge as bridge  # noqa: E402
import heartbeat_outcome as ho  # noqa: E402


DRAFT = {
    "id": "abc123",
    "status": "draft",
    "title": "IA open source vale a pena?",
    "custom_excerpt": "O que muda para quem vende.",
    "url": "https://blog.sistemabritto.com.br/p/uuid-preview/",
    "feature_image": "https://blog.sistemabritto.com.br/content/images/capa.png",
    "plaintext": "corpo " * 400,
    "html": ('<p>Texto <a href="https://sistemabritto.com.br/whatsapp">fala com a gente</a> '
             'e <a href="https://blog.sistemabritto.com.br/outro/">outro artigo</a> '
             'e <a href="https://exemplo.com/fonte">fonte</a>.</p>'),
    "updated_at": "2026-07-25T20:00:00.000Z",
}


# ── o que o humano vê para decidir ───────────────────────────────────────

def test_separa_cta_de_funil_de_link_externo(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    ctas = gp.ctas_do_artigo(DRAFT)
    assert ctas["funis"] == ["https://sistemabritto.com.br/whatsapp"]
    assert ctas["externos"] == ["https://exemplo.com/fonte"]
    assert ctas["internos"] == ["https://blog.sistemabritto.com.br/outro/"]


def test_resumo_mostra_o_cta_para_conferir_antes_de_publicar(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    texto = gp.resumo_para_aprovacao(DRAFT)
    assert "sistemabritto.com.br/whatsapp" in texto
    assert "IA open source vale a pena?" in texto


def test_artigo_sem_cta_avisa_em_vez_de_passar_batido(monkeypatch):
    """Informa e não converte é erro que só aparece depois de publicado."""
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    sem_cta = {**DRAFT, "html": '<p><a href="https://exemplo.com/x">fonte</a></p>'}
    assert "NENHUM CTA" in gp.resumo_para_aprovacao(sem_cta)


def test_artigo_sem_capa_avisa(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    assert "SEM imagem de capa" in gp.resumo_para_aprovacao({**DRAFT, "feature_image": ""})


# ── o gate ───────────────────────────────────────────────────────────────

@pytest.fixture
def ghost_falso(monkeypatch):
    monkeypatch.setenv("GHOST_URL", "https://blog.sistemabritto.com.br")
    monkeypatch.setattr(gp, "buscar", lambda _id: DRAFT)
    return DRAFT


def test_gate_do_blog_carrega_o_id_do_artigo_e_nao_so_o_texto(ghost_falso):
    r = bridge.aprovar_artigo("abc123", dry_run=True)
    o = r["outcome"]
    assert o["publish_target"] == "blog"
    assert o["publish_ref"] == "abc123", "sem o id não há o que publicar"
    assert o["publish_content"] != o["publish_ref"]


def test_gate_do_blog_leva_capa_e_preview(ghost_falso):
    o = bridge.aprovar_artigo("abc123", dry_run=True)["outcome"]
    assert o["publish_media"] == [DRAFT["feature_image"]]
    assert o["source_url"] == DRAFT["url"], "o preview do draft abre sem login"


def test_artigo_ja_publicado_nao_abre_gate_de_novo(monkeypatch):
    monkeypatch.setattr(gp, "buscar", lambda _id: {**DRAFT, "status": "published"})
    r = bridge.aprovar_artigo("abc123", dry_run=True)
    assert r["ok"] is True and "ignorado" in r


def test_post_inexistente_falha_claro(monkeypatch):
    monkeypatch.setattr(gp, "buscar", lambda _id: None)
    r = bridge.aprovar_artigo("sumiu", dry_run=True)
    assert r["ok"] is False and "não encontrado" in r["erro"]


# ── execução da aprovação ────────────────────────────────────────────────

def test_blog_publica_pelo_ghost_e_nao_pelo_postiz(monkeypatch):
    chamou = {}
    monkeypatch.setattr(gp, "publicar",
                        lambda ref, quando=None: chamou.update(ref=ref, quando=quando)
                        or {"published": True, "detail": "publicado."})
    r = ho._run_blog_publish({"publish_ref": "abc123", "publish_at": None})
    assert r["published"] is True
    assert chamou["ref"] == "abc123"


def test_sem_publish_ref_recusa_em_vez_de_adivinhar():
    r = ho._run_blog_publish({"publish_content": "resumo bonito"})
    assert r["published"] is False and "publish_ref" in r["detail"]


def test_data_no_passado_e_recusada():
    r = ho._run_blog_publish({"publish_ref": "abc", "publish_at": "2020-01-01T00:00:00Z"})
    assert r["published"] is False and "passado" in r["detail"]


def test_blog_e_canal_valido_do_gate():
    assert "blog" in ho.PUBLISH_CHANNELS


# ── ordem dos estágios ───────────────────────────────────────────────────

def test_ponte_das_redes_recusa_artigo_nao_publicado(monkeypatch):
    """A garantia central: rede nunca deriva de artigo em draft."""
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: DRAFT)
    r = bridge.distribuir("abc123", dry_run=True)
    assert r.get("ignorado"), f"deveria recusar draft, devolveu {r}"
    assert not r.get("redes")


def test_ponte_das_redes_aceita_publicado(monkeypatch):
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {**DRAFT, "status": "published"})
    monkeypatch.setenv("XAI_API_KEY", "")
    r = bridge.distribuir("abc123", dry_run=True)
    assert set(r["redes"]) == set(bridge.REDES)


# ── refazer o artigo (pedido do Felipe, 26/07) ───────────────────────────

def test_feedback_so_sobre_capa_nao_reescreve_o_texto():
    """Trocar um texto que o humano já aprovou por outro que ele não pediu é
    regressão disfarçada de melhoria. O feedback real foi: 'o texto está
    aprovado, mas sem a thumbnail não dá'."""
    so_imagem = "Essa foto ficou ruim, gera outra thumbnail melhor"
    assert gp._e_sobre_imagem(so_imagem) is True
    assert gp._e_sobre_texto(so_imagem) is False


def test_feedback_sobre_os_dois_refaz_os_dois():
    misto = "Falta thumbnail e o texto ficou meio careta, humaniza mais"
    assert gp._e_sobre_imagem(misto) is True
    assert gp._e_sobre_texto(misto) is True


def test_feedback_so_de_texto_nao_gasta_geracao_de_imagem():
    so_texto = "O gancho tá fraco e falta CTA pro funil"
    assert gp._e_sobre_texto(so_texto) is True
    assert gp._e_sobre_imagem(so_texto) is False


def test_revisao_truncada_e_descartada(monkeypatch):
    """Metade do original já é regressão, não revisão — melhor manter o texto
    atual do que substituir por um pedaço."""
    monkeypatch.setattr(gp, "_pedir_ao_modelo", lambda *a, **k: "<p>curto</p>")
    assert gp.revisar_texto({"title": "T", "html": "<p>" + "x" * 5000 + "</p>"}, "melhora") == ""


def test_sem_modelo_configurado_mantem_o_texto(monkeypatch):
    monkeypatch.setattr(gp, "_pedir_ao_modelo", lambda *a, **k: "")
    assert gp.revisar_texto({"title": "T", "html": "<p>original</p>"}, "muda") == ""


def test_briefing_de_capa_tem_fallback_sem_modelo(monkeypatch):
    """Modelo fora do ar não pode impedir a capa de ser gerada."""
    monkeypatch.setattr(gp, "_pedir_ao_modelo", lambda *a, **k: "")
    b = gp.briefing_de_capa({"title": "Disparo em massa: o que bane seu número"})
    assert b["headline"] and b["hook"] and b["expressao"]


def test_refacao_do_blog_respeita_o_teto(monkeypatch):
    import ghost_social_bridge as br

    r = br.refazer_artigo({"publish_ref": "abc"}, "muda", "tkt",
                          tentativa=br.MAX_REFACOES + 1)
    assert r["ok"] is False and "teto" in r["erro"]


def test_blog_entra_na_refacao_automatica():
    """Antes o blog era excluído de propósito; o Felipe apontou que isso deixa
    o fluxo incompleto — criticar e não acontecer nada é pior que não ter o
    botão."""
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def _agendar_refacao")[1]
    assert '"blog"' in trecho
    assert "refazer_artigo" in trecho


# ── aprovar deriva as redes sem depender de webhook ──────────────────────

def test_publicar_dispara_a_derivacao_sem_webhook():
    """Criar webhook no Ghost exige sessão de staff — chave de API devolve
    403/404. Depender dele significaria: aprovar o artigo e as redes não
    acontecerem, sem erro nenhum."""
    fonte = (REPO_ROOT / "dashboard" / "backend" / "heartbeat_outcome.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def _run_blog_publish")[1].split("def _run_publish_action")[0]
    assert "_derivar_redes_em_background" in trecho


def test_agendado_nao_deriva_ainda(monkeypatch):
    """Artigo agendado não está no ar; derivar agora publicaria post de rede
    apontando para uma página que ainda não existe."""
    chamou = []
    monkeypatch.setattr(ho, "_derivar_redes_em_background", lambda p: chamou.append(p))
    monkeypatch.setattr(gp, "publicar",
                        lambda ref, quando=None: {"published": True, "status": "scheduled",
                                                  "detail": "agendado"})
    ho._run_blog_publish({"publish_ref": "abc", "publish_at": None})
    assert chamou == []


def test_publicado_agora_deriva(monkeypatch):
    chamou = []
    monkeypatch.setattr(ho, "_derivar_redes_em_background", lambda p: chamou.append(p))
    monkeypatch.setattr(gp, "publicar",
                        lambda ref, quando=None: {"published": True, "status": "published",
                                                  "detail": "publicado"})
    ho._run_blog_publish({"publish_ref": "abc", "publish_at": None})
    assert chamou == ["abc"]


def test_falha_ao_publicar_nao_deriva(monkeypatch):
    chamou = []
    monkeypatch.setattr(ho, "_derivar_redes_em_background", lambda p: chamou.append(p))
    monkeypatch.setattr(gp, "publicar",
                        lambda ref, quando=None: {"published": False, "detail": "erro"})
    ho._run_blog_publish({"publish_ref": "abc", "publish_at": None})
    assert chamou == []


# ── o rosto certo ────────────────────────────────────────────────────────

def test_face_bank_aponta_para_as_fotos_reais():
    """A capa saiu com a cara de outra pessoa porque o primer dizia que a
    referência de ESTILO era foto do Felipe."""
    import thumbnail_maker as tm

    assert tm.ROSTO_PADRAO.is_file(), f"foto de referência ausente: {tm.ROSTO_PADRAO}"
    assert "thumbnail-refs" not in str(tm.ROSTO_PADRAO), "essa pasta é referência de estilo"
    assert "faces" in str(tm.FACE_BANK)


def test_primer_avisa_que_a_referencia_nao_e_o_felipe():
    primer = (REPO_ROOT / ".claude" / "skills" / "social-ai-trends-blog" / "assets"
              / "THUMBNAIL-PRIMER.md").read_text(encoding="utf-8")
    assert "NÃO é foto do Felipe" in primer
    assert "library/images/faces" in primer


def test_prompt_ancora_os_tracos_do_rosto():
    import thumbnail_maker as tm

    p = tm.montar_prompt("TESTE", "um celular")
    assert "sem óculos" in p, "a referência de estilo usa óculos; o rosto certo não"
    assert "terço DIREITO" in p
    assert "A3E635" in p, "verde-limão é a cor da marca"


# ── o card precisa provar que o artigo mudou ─────────────────────────────
# 2026-07-26: o Felipe pediu para reescrever um artigo com o humanizer. O texto
# foi reescrito inteiro (1492 → 1308 palavras, tom bem melhor) e o card voltou
# com a mesma cara — título, excerpt, CTA e contagem são quase invariantes a uma
# reescrita de corpo. Ele concluiu que o sistema tinha devolvido o mesmo artigo.

def test_resumo_mostra_a_abertura_do_artigo(monkeypatch):
    """Tom é o que se valida neste gate, e tom só se julga lendo o texto."""
    import ghost_publisher as gp

    post = {
        "title": "Disparo em massa no WhatsApp",
        "status": "draft",
        "custom_excerpt": "Resumo curto que não muda quando o corpo é reescrito.",
        "feature_image": "https://blog.local/capa.png",
        "html": '<p>x</p><a href="https://sistemabritto.com.br/whatsapp">CTA</a>',
        "plaintext": ("Disparo em massa no WhatsApp é permitido, sim. Você pode mandar "
                      "mensagem para muita gente desde que cada pessoa tenha te passado o "
                      "número dela e dado autorização clara. A política oficial é direta: "
                      "só vale falar com quem forneceu o telefone e confirmou que quer "
                      "receber. Lista comprada não conta como autorização de ninguém."),
    }
    resumo = gp.resumo_para_aprovacao(post)
    assert "começa assim" in resumo
    assert "Disparo em massa no WhatsApp é permitido, sim." in resumo


def test_abertura_diferente_muda_o_resumo(monkeypatch):
    """A regressão concreta: dois textos distintos produziam o mesmo card."""
    import ghost_publisher as gp

    base = {"title": "T", "status": "draft", "custom_excerpt": "Mesmo excerpt.",
            "feature_image": "https://blog.local/c.png",
            "html": '<a href="https://sistemabritto.com.br/whatsapp">CTA</a>'}
    a = gp.resumo_para_aprovacao({**base, "plaintext": "Primeira versão do texto. " * 12})
    b = gp.resumo_para_aprovacao({**base, "plaintext": "Segunda versão, bem diferente. " * 12})
    assert a != b


def test_artigo_sem_corpo_nao_inventa_abertura():
    import ghost_publisher as gp

    resumo = gp.resumo_para_aprovacao({
        "title": "T", "status": "draft", "custom_excerpt": "E.",
        "feature_image": "https://blog.local/c.png", "html": "", "plaintext": "",
    })
    assert "começa assim" not in resumo
