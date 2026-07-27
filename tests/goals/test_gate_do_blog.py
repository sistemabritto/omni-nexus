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
    # Expressão fica de fora: o registro sorteado pelo rodízio já descreve a
    # cara, e o antigo fallback "sorriso confiante" era o que fazia toda capa
    # sair igual quando o modelo não detalhava.
    assert b["headline"] and b["hook"]


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

# O banco de rostos é acervo pessoal e não vai para o repositório — no CI a
# pasta não existe. Os testes que dependem do arquivo em disco são pulados lá;
# os que verificam a lógica (rodízio de pose, lado, determinismo) rodam sempre,
# porque não abrem imagem nenhuma.
def _sem_banco_de_rostos() -> bool:
    import thumbnail_maker as tm

    return not tm.FACE_BANK.is_dir()


precisa_das_fotos = pytest.mark.skipif(
    _sem_banco_de_rostos(), reason="banco de rostos não versionado (ausente no CI)")


@precisa_das_fotos
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


# ── nem toda capa pode ter a mesma cara ──────────────────────────────────
# 2026-07-27: "a thumbnail tá vindo muito parecida... o que não dá é pra sair
# todas as thumb com a mesma cara e pose". Era literal: uma única foto de
# referência, "terço DIREITO" fixo no prompt e "sorriso confiante" como
# fallback de expressão em toda capa que o modelo não descrevesse.

@precisa_das_fotos
def test_todas_as_poses_do_banco_existem_em_disco():
    """Referência ausente derruba a capa inteira — e falha tarde, na API."""
    import thumbnail_maker as tm

    faltando = [p["arquivo"].name for p in tm.POSES if not p["arquivo"].is_file()]
    assert faltando == []


def test_nenhuma_pose_vem_de_foto_com_outra_pessoa():
    """`/v1/images/edits` com foto de grupo pode escolher o rosto errado — foi
    exatamente o erro que este módulo existe para não repetir."""
    import thumbnail_maker as tm

    assert [p["arquivo"].name for p in tm.POSES if "family" in p["arquivo"].name] == []


def test_capas_vizinhas_nunca_repetem_pose_nem_expressao():
    import thumbnail_maker as tm

    for n in range(24):
        a, b = tm.variacao_de(n), tm.variacao_de(n + 1)
        assert a["pose"]["arquivo"] != b["pose"]["arquivo"], f"pose repetida em {n}→{n+1}"
        assert a["registro"] != b["registro"], f"registro repetido em {n}→{n+1}"


def test_uma_semana_de_esteira_varre_o_banco_de_poses():
    """21 pautas por ciclo têm de passar por todas as poses, não por duas."""
    import thumbnail_maker as tm

    usadas = {tm.variacao_de(n)["pose"]["arquivo"] for n in range(1, 22)}
    assert len(usadas) == len(tm.POSES)


def test_o_lado_do_quadro_tambem_alterna():
    import thumbnail_maker as tm

    lados = {tm.variacao_de(n)["lado"] for n in range(1, 22)}
    assert lados == set(tm.LADOS)


def test_a_mesma_pauta_gera_sempre_a_mesma_capa():
    """Determinismo é o que faz retry não virar arte nova a cada tentativa."""
    import thumbnail_maker as tm

    assert tm.variacao_de(7) == tm.variacao_de(7)
    assert tm.montar_prompt("X", "y", variacao=7) == tm.montar_prompt("X", "y", variacao=7)


def test_o_prompt_muda_de_verdade_entre_variacoes():
    import thumbnail_maker as tm

    prompts = {tm.montar_prompt("MESMO TEXTO", "mesmo hook", variacao=n) for n in range(8)}
    assert len(prompts) == 8


def test_o_texto_vai_para_o_lado_oposto_ao_rosto():
    """Rosto e headline no mesmo terço é capa ilegível em miniatura."""
    import thumbnail_maker as tm

    for n in range(8):
        p = tm.montar_prompt("HEADLINE", "hook", variacao=n)
        lado = tm.variacao_de(n)["lado"]
        oposto = "esquerdo" if lado == "DIREITO" else "direito"
        assert f"terço {lado}" in p
        assert f"TEXTO GRANDE no lado {oposto}" in p


def test_briefing_recebe_o_registro_sorteado(monkeypatch):
    """Sem isto o modelo devolve "sorriso confiante" em toda capa."""
    import ghost_publisher as gp
    import thumbnail_maker as tm

    visto = {}
    monkeypatch.setattr(gp, "_pedir_ao_modelo", lambda p, **k: visto.setdefault("prompt", p) and "")
    gp.briefing_de_capa({"title": "Artigo"}, registro=tm.REGISTROS[2])
    assert tm.REGISTROS[2] in visto["prompt"]


def test_expressao_nao_tem_mais_fallback_fixo(monkeypatch):
    import ghost_publisher as gp

    monkeypatch.setattr(gp, "_pedir_ao_modelo", lambda p, **k: "não é json")
    assert gp.briefing_de_capa({"title": "Artigo"})["expressao"] == ""


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


# ── um gate por artigo, não um por execução ──────────────────────────────
# 2026-07-26: o pipeline foi reprocessado três vezes corrigindo defeitos e
# abriu três gates do MESMO artigo. O Felipe recebeu as três aprovações e teve
# de rejeitar uma a uma. Notificação repetida não é só ruído — ensina a ignorar
# o canal, e é esse canal que sustenta o human-in-the-loop.

def test_nao_abre_gate_se_ja_existe_um_pendente(monkeypatch):
    import ghost_social_bridge as bridge
    import sdk_client

    post = {"id": "post-1", "title": "Artigo", "status": "draft",
            "url": "https://blog.local/p/x/", "html": "<p>corpo</p>", "plaintext": "corpo"}
    monkeypatch.setattr("ghost_publisher.buscar", lambda _id: post)

    criados = []

    class _Evo:
        def get(self, path, params=None):
            return {"approvals": [
                {"id": 27, "publish": {"publish_ref": "post-1", "target": "blog"}},
            ]}

        def post(self, path, json=None):
            criados.append(path)
            return {"id": "novo"}

    monkeypatch.setattr(sdk_client, "evo", _Evo())
    r = bridge.aprovar_artigo("post-1")
    assert r["ok"] is True
    assert "já existe gate pendente" in r["ignorado"]
    assert r["aprovacao"] == 27
    assert criados == [], "não podia ter criado ticket nem aprovação"


def test_gate_de_outro_artigo_nao_bloqueia(monkeypatch):
    """Só o MESMO artigo bloqueia — senão um gate pendente travaria a esteira
    inteira e a semana pararia no primeiro post."""
    import ghost_social_bridge as bridge
    import sdk_client

    post = {"id": "post-2", "title": "Outro", "status": "draft",
            "url": "https://blog.local/p/y/", "html": "<p>c</p>", "plaintext": "c"}
    monkeypatch.setattr("ghost_publisher.buscar", lambda _id: post)

    class _Evo:
        def get(self, path, params=None):
            return {"approvals": [{"id": 27, "publish": {"publish_ref": "post-1"}}]}

        def post(self, path, json=None):
            return {"id": "tkt-1"}

    monkeypatch.setattr(sdk_client, "evo", _Evo())
    r = bridge.aprovar_artigo("post-2")
    assert "ignorado" not in r


def test_api_indisponivel_nao_trava_a_publicacao(monkeypatch):
    """Sem a checagem, o pior caso é o gate duplicado — melhor que não publicar."""
    import ghost_social_bridge as bridge
    import sdk_client

    post = {"id": "post-3", "title": "T", "status": "draft",
            "url": "https://blog.local/p/z/", "html": "<p>c</p>", "plaintext": "c"}
    monkeypatch.setattr("ghost_publisher.buscar", lambda _id: post)

    class _Evo:
        def get(self, path, params=None):
            raise RuntimeError("api fora do ar")

        def post(self, path, json=None):
            return {"id": "tkt-1"}

    monkeypatch.setattr(sdk_client, "evo", _Evo())
    assert "ignorado" not in bridge.aprovar_artigo("post-3")


def test_dry_run_nao_consulta_a_api(monkeypatch):
    import ghost_social_bridge as bridge
    import sdk_client

    post = {"id": "post-4", "title": "T", "status": "draft",
            "url": "https://blog.local/p/w/", "html": "<p>c</p>", "plaintext": "c"}
    monkeypatch.setattr("ghost_publisher.buscar", lambda _id: post)

    class _Evo:
        def get(self, path, params=None):
            raise AssertionError("dry_run não deveria consultar a API")

    monkeypatch.setattr(sdk_client, "evo", _Evo())
    assert bridge.aprovar_artigo("post-4", dry_run=True)["dry_run"] is True


def test_preview_expoe_o_publish_ref():
    """É o campo que permite descobrir o gate duplicado."""
    from routes.approvals import _render_publish_preview

    p = _render_publish_preview("publish", {"outcome": {
        "publish_target": "blog", "publish_ref": "post-1",
        "publish_content": "resumo", "publish_media": []}})
    assert p["publish_ref"] == "post-1"
