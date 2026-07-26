"""
tests/goals/test_esteira_de_conteudo.py

2026-07-26 — a ponte pauta → artigo, que era o elo manual da esteira.

O research levantava a pauta e o gate sabia publicar, mas ninguém escrevia o
artigo no meio. Por isso o ciclo parava todo dia esperando alguém sentar e
escrever.

Run:
    pytest tests/goals/test_esteira_de_conteudo.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import escritor_de_artigo as escritor  # noqa: E402


PAUTA = {"id": 1, "prioridade": 1, "keyword": "chatbot whatsapp para empresas",
         "volume": 1300, "kd": 21.5, "data_alvo": "2026-07-27",
         "publish_at": "2026-07-27T12:00:00Z"}


def _artigo_valido(html_extra: str = "", url_funil: str = "https://sistemabritto.com.br/whatsapp"):
    corpo = "<p>" + ("palavra " * 700) + "</p>"
    return json.dumps({
        "titulo": "Chatbot WhatsApp para empresas: vale a pena?",
        "excerpt": "Resposta curta com o que muda na operação.",
        "html": corpo + html_extra + f'<p><a href="{url_funil}">veja como a gente faz</a></p>',
    })


# ── escolha do funil ─────────────────────────────────────────────────────

@pytest.mark.parametrize("keyword,esperado", [
    ("chatbot whatsapp para empresas", "whatsapp"),
    ("disparo em massa no whatsapp", "whatsapp"),
    ("como gerar lead qualificado", "whatsapp"),
    ("agendar post no instagram", "socialjobs"),
    ("crescer no tiktok organicamente", "socialjobs"),
    ("ganhar seguidor no youtube", "socialjobs"),
    ("automatizar o financeiro da empresa", "sistema"),
])
def test_funil_e_escolhido_pelo_assunto(keyword, esperado):
    """Regra explícita em vez de deixar o modelo inventar: CTA genérico não converte."""
    url, _ = escritor._funil_para(keyword)
    assert url.endswith(f"/{esperado}")


def test_assunto_desconhecido_cai_no_guarda_chuva():
    url, _ = escritor._funil_para("assunto que ninguém previu")
    assert url.endswith("/sistema")


# ── o prompt carrega as regras que viraram exigência ─────────────────────

def test_prompt_inclui_o_humanizer():
    """'Todo blog post deve ser escrito usando a Skill Humanizer' virou regra.

    Antes o guia só entrava na REVISÃO, depois que o Felipe reclamava do tom —
    o artigo nascia careta e alguém precisava pedir ajuste para corrigir.
    """
    prompt = escritor.montar_prompt(PAUTA)
    assert "ANTI-ESCRITA-DE-IA" in prompt
    assert len(prompt) > 2000, "o humanizer não foi carregado no prompt"


def test_prompt_exige_cta_do_funil_certo():
    prompt = escritor.montar_prompt(PAUTA)
    assert "https://sistemabritto.com.br/whatsapp" in prompt
    assert "CTA OBRIGATÓRIO" in prompt


def test_prompt_carrega_as_regras_de_geo():
    """É o que faz a LLM citar o artigo, não só indexar."""
    prompt = escritor.montar_prompt(PAUTA)
    assert "DOIS primeiros parágrafos" in prompt
    assert "fonte" in prompt.lower()


def test_gancho_de_noticia_entra_quando_existe():
    prompt = escritor.montar_prompt(PAUTA, noticia="A Meta anunciou X na terça.")
    assert "A Meta anunciou X na terça." in prompt


def test_prompt_proibe_os_termos_de_marca():
    prompt = escritor.montar_prompt(PAUTA)
    for proibido in ("revolucionar", "transformação digital", "garanta já"):
        assert proibido in prompt, f"{proibido} deveria estar na lista de proibições"


# ── a escrita em si ──────────────────────────────────────────────────────

def test_escreve_o_artigo(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: _artigo_valido())
    artigo, erro = escritor.escrever(PAUTA)
    assert erro == ""
    assert artigo["titulo"].startswith("Chatbot WhatsApp")
    assert artigo["palavras"] >= escritor.MINIMO_DE_PALAVRAS


def test_json_dentro_de_cerca_de_codigo_e_aceito(monkeypatch):
    """O modelo insiste em embrulhar em ```json apesar da instrução."""
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: f"```json\n{_artigo_valido()}\n```")
    artigo, erro = escritor.escrever(PAUTA)
    assert erro == ""
    assert artigo["html"]


def test_json_com_texto_em_volta_e_resgatado(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: f"Claro! Aqui está:\n{_artigo_valido()}\nEspero ter ajudado.")
    _, erro = escritor.escrever(PAUTA)
    assert erro == ""


def test_artigo_curto_e_recusado(monkeypatch):
    """300 palavras não é artigo, é resumo — e gastaria o slot da semana."""
    curto = json.dumps({"titulo": "T", "excerpt": "E", "html": "<p>" + "x " * 50 + "</p>"})
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: curto)
    artigo, erro = escritor.escrever(PAUTA)
    assert artigo == {}
    assert "curto demais" in erro


def test_resposta_vazia_do_modelo_e_erro_explicito(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: "")
    artigo, erro = escritor.escrever(PAUTA)
    assert artigo == {}
    assert "não respondeu" in erro


def test_json_quebrado_nao_vira_artigo(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo",
                        lambda p, timeout=0: "isso não é json nem de longe")
    artigo, erro = escritor.escrever(PAUTA)
    assert artigo == {}
    assert "titulo ou html" in erro


def test_artigo_sem_titulo_e_recusado(monkeypatch):
    sem_titulo = json.dumps({"titulo": "", "html": "<p>" + "x " * 700 + "</p>"})
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: sem_titulo)
    assert escritor.escrever(PAUTA)[0] == {}


def test_cta_ausente_e_anexado_em_vez_de_perder_o_artigo(monkeypatch):
    """O texto está bom; perder tudo por causa de um link seria desperdício."""
    sem_cta = json.dumps({
        "titulo": "Título válido", "excerpt": "E",
        "html": "<p>" + ("palavra " * 700) + "</p>",
    })
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: sem_cta)
    artigo, erro = escritor.escrever(PAUTA)
    assert erro == ""
    assert "https://sistemabritto.com.br/whatsapp" in artigo["html"]


def test_cta_presente_nao_e_duplicado(monkeypatch):
    monkeypatch.setattr("ghost_publisher._pedir_ao_modelo", lambda p, timeout=0: _artigo_valido())
    artigo, _ = escritor.escrever(PAUTA)
    assert artigo["html"].count("https://sistemabritto.com.br/whatsapp") == 1


def test_cta_do_funil_errado_nao_conta(monkeypatch):
    """Artigo de WhatsApp linkando /socialjobs manda o lead para o funil errado."""
    monkeypatch.setattr(
        "ghost_publisher._pedir_ao_modelo",
        lambda p, timeout=0: _artigo_valido(url_funil="https://sistemabritto.com.br/socialjobs"))
    artigo, erro = escritor.escrever(PAUTA)
    assert erro == ""
    assert "https://sistemabritto.com.br/whatsapp" in artigo["html"]


# ── criação do rascunho no Ghost ─────────────────────────────────────────

class _Resposta:
    def __init__(self, status, corpo):
        self.status_code = status
        self._corpo = corpo
        self.text = json.dumps(corpo)

    def json(self):
        return self._corpo


def test_rascunho_nasce_draft_nunca_publicado(monkeypatch):
    """Criar já publicado tiraria do humano a decisão que o gate existe para dar."""
    import ghost_publisher as gp

    enviado = {}

    def _post(url, headers=None, json=None, timeout=0):
        enviado["url"] = url
        enviado["corpo"] = json["posts"][0]
        return _Resposta(201, {"posts": [{"id": "novo-123"}]})

    monkeypatch.setattr(gp, "_config", lambda: ("https://blog.local", "k"))
    monkeypatch.setattr(gp, "_headers", lambda k: {})
    monkeypatch.setattr(gp.requests, "post", _post)

    post_id, erro = gp.criar_rascunho("Título", "<p>corpo</p>", excerpt="resumo")
    assert (post_id, erro) == ("novo-123", "")
    assert enviado["corpo"]["status"] == "draft"
    assert enviado["corpo"]["custom_excerpt"] == "resumo"
    # Sem ?source=html o Ghost devolve 201 e descarta o corpo em silêncio.
    assert "source=html" in enviado["url"]


def test_ghost_recusando_o_rascunho_vira_erro(monkeypatch):
    import ghost_publisher as gp

    monkeypatch.setattr(gp, "_config", lambda: ("https://blog.local", "k"))
    monkeypatch.setattr(gp, "_headers", lambda k: {})
    monkeypatch.setattr(gp.requests, "post",
                        lambda *a, **k: _Resposta(422, {"errors": [{"message": "inválido"}]}))
    post_id, erro = gp.criar_rascunho("T", "<p>x</p>")
    assert post_id == ""
    assert "422" in erro


def test_ghost_sem_id_no_retorno_vira_erro(monkeypatch):
    """201 sem id é falha silenciosa — a pauta ficaria órfã do rascunho."""
    import ghost_publisher as gp

    monkeypatch.setattr(gp, "_config", lambda: ("https://blog.local", "k"))
    monkeypatch.setattr(gp, "_headers", lambda k: {})
    monkeypatch.setattr(gp.requests, "post", lambda *a, **k: _Resposta(201, {"posts": []}))
    assert gp.criar_rascunho("T", "<p>x</p>")[0] == ""


def test_sem_credencial_do_ghost_nao_finge_sucesso(monkeypatch):
    import ghost_publisher as gp

    monkeypatch.setattr(gp, "_config", lambda: None)
    post_id, erro = gp.criar_rascunho("T", "<p>x</p>")
    assert post_id == ""
    assert "GHOST_URL" in erro


# ── dedupe: não canibalizar o próprio blog ───────────────────────────────
# Na primeira execução real, "respostas automaticas whatsapp" e "resposta
# automatica whatsapp" saíram juntas na fila — e o blog tinha publicado
# exatamente esse tema naquele mesmo dia. Duas pautas quase idênticas na
# mesma semana disputam a mesma busca entre si e gastam dois dos 21 slots.

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "weekly_content_research", REPO_ROOT / "ADWs" / "routines" / "weekly_content_research.py")
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)


def _kw(texto: str, vol: int = 500) -> dict:
    return {"kw": texto, "vol": vol, "kd": 20}


def test_plural_e_acento_nao_criam_assunto_novo():
    """O par exato que passou batido na primeira execução."""
    sobraram = research.descartar_repetidas(
        [_kw("respostas automaticas whatsapp"), _kw("resposta automática whatsapp")], [])
    assert len(sobraram) == 1


def test_descarta_o_que_o_blog_ja_publicou():
    sobraram = research.descartar_repetidas(
        [_kw("resposta automatica no whatsapp"), _kw("agendar story instagram")],
        ["Resposta automática no WhatsApp: como configurar sem parecer robô"])
    assert [k["kw"] for k in sobraram] == ["agendar story instagram"]


def test_assuntos_diferentes_sobrevivem():
    """Compartilhar 'whatsapp' não faz de duas pautas a mesma pauta."""
    entrada = [_kw("plano whatsapp business"), _kw("grupos de whatsapp marketing"),
               _kw("agendar story instagram")]
    assert len(research.descartar_repetidas(entrada, [])) == 3


def test_ordem_de_prioridade_e_preservada():
    """A primeira da lista é a de melhor retorno; ela deve vencer o empate."""
    entrada = [_kw("chatbot whatsapp para empresas", 1900),
               _kw("chatbot de whatsapp para empresa", 300)]
    sobraram = research.descartar_repetidas(entrada, [])
    assert [k["vol"] for k in sobraram] == [1900]


def test_lista_de_cobertos_vazia_nao_descarta_nada():
    entrada = [_kw("a"), _kw("assunto um qualquer"), _kw("outro tema distinto aqui")]
    assert len(research.descartar_repetidas(entrada, [])) >= 2


def test_palavras_vazias_nao_decidem_colisao():
    """Sem remover 'de/para/com', quase tudo pareceria parente."""
    nucleo = research._nucleo("o plano de whatsapp para a empresa")
    assert "de" not in nucleo and "para" not in nucleo
    assert {"plano", "whatsapp", "empresa"} <= nucleo


# ── seeds: diversidade é o que sustenta 21 pautas por semana ─────────────

def test_seeds_cobrem_os_tres_funis():
    """Pauta sem funil claro é tráfego sem destino."""
    seeds = research.seeds_da_semana(__import__("datetime").date(2026, 7, 26))
    assert len(seeds) == research.SEEDS_POR_RODADA * len(research.SEEDS_POR_FUNIL)
    assert len(set(seeds)) == len(seeds), "seed repetida desperdiça uma consulta"


def test_seeds_giram_entre_semanas():
    """Bater sempre nas mesmas cinco é como o blog acabava repetindo assunto."""
    from datetime import date

    a = research.seeds_da_semana(date(2026, 7, 26))
    b = research.seeds_da_semana(date(2026, 8, 9))
    assert a != b


def test_seeds_sao_estaveis_dentro_da_mesma_semana():
    """Duas execuções na mesma semana pedem as mesmas seeds — previsível."""
    from datetime import date

    assert research.seeds_da_semana(date(2026, 7, 27)) == research.seeds_da_semana(date(2026, 8, 1))


def test_rotacao_nunca_estoura_o_grupo():
    """Qualquer semana do ano tem de devolver seeds válidas."""
    from datetime import date, timedelta

    dia = date(2026, 1, 1)
    while dia.year == 2026:
        seeds = research.seeds_da_semana(dia)
        assert len(seeds) == research.SEEDS_POR_RODADA * len(research.SEEDS_POR_FUNIL)
        dia += timedelta(days=7)


# ── o filtro que separa pauta de lixo ────────────────────────────────────

def _aprovada(kw: str) -> bool:
    return (bool(research.COMPRA.search(kw)) and bool(research.DOMINIO.search(kw))
            and not research.RUIDO.search(kw))


@pytest.mark.parametrize("kw", [
    # O caso real: "api" sem \b casava dentro de "jaPInha", e esta entrou como
    # pauta nº 1 da primeira fila de verdade, com 14.800 buscas/mês.
    "japinha do cv instagram",
    "analista de sistemas jr",
    "tecnico em desenvolvimento de sistemas",
    "analise e desenvolvimento de sistemas ead",
    "caixa ferramenta plastica",
    "salvador digital agendamento cadastro unico",
    "sistemas cad cam",
    "curso de marketing digital gratis",
])
def test_lixo_nao_vira_pauta(kw):
    """Volume alto não é sinal de pauta boa quando a busca vem de outro público."""
    assert not _aprovada(kw), f"{kw!r} passou pelo filtro"


@pytest.mark.parametrize("kw", [
    "api whatsapp business",
    "como automatizar o whatsapp de graça",
    "melhor horário para postar no instagram",
    "software para envio de whatsapp em massa",
    "chatbot whatsapp para empresas",
    "agente de ia para atendimento",
])
def test_pauta_boa_passa(kw):
    assert _aprovada(kw), f"{kw!r} foi barrada indevidamente"


def test_dominio_e_exigido_alem_da_intencao_comercial():
    """'sistema' e 'ferramenta' sozinhos aparecem em busca de curso técnico
    e de caixa de plástico — a intenção comercial não basta."""
    assert research.COMPRA.search("melhor sistema de gestao escolar")
    assert not _aprovada("melhor sistema de gestao escolar")


def test_prompt_diz_o_ano_corrente():
    """O corte de treino do modelo é anterior a hoje: o primeiro artigo real
    saiu como '…em 2025' enquanto o blog publicava em 2026. Ano errado no
    título envelhece o post no dia em que ele nasce."""
    from datetime import date

    prompt = escritor.montar_prompt(PAUTA)
    assert str(date.today().year) in prompt
    assert "HOJE É" in prompt


def test_upload_de_capa_usa_a_funcao_de_jwt_que_existe(monkeypatch, tmp_path):
    """`ghost_jwt` nunca existiu neste módulo (é do ghost_social_bridge). O
    NameError caía no except genérico e virava "name 'ghost_jwt' is not
    defined" travestido de erro de rede — nenhuma capa da esteira jamais subiu.
    """
    import ghost_publisher as gp

    imagem = tmp_path / "capa.png"
    imagem.write_bytes(b"png")
    monkeypatch.setattr(gp, "_config", lambda: ("https://blog.local", "id:segredo"))
    monkeypatch.setattr(gp, "_jwt", lambda k: "token-falso")
    monkeypatch.setattr(gp.requests, "post",
                        lambda *a, **k: _Resposta(200, {"images": [{"url": "/content/capa.png"}]}))

    url, erro = gp.subir_imagem(imagem)
    assert erro == ""
    assert url == "https://blog.local/content/capa.png"
