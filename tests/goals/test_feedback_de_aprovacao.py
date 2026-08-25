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


# ── refazer no ato (pedido do Felipe, 25/07) ─────────────────────────────

@pytest.fixture
def bridge_com_api(monkeypatch):
    """Bridge com Ghost e API falsos, para exercitar refazer() sem rede."""
    import sys as _sys
    import types as _types

    import ghost_social_bridge as bridge

    chamadas = []

    class _Evo:
        @staticmethod
        def post(rota, corpo):
            chamadas.append((rota, corpo))
            return {"id": 99}

    fake = _types.ModuleType("sdk_client")
    fake.evo = _Evo()
    monkeypatch.setitem(_sys.modules, "sdk_client", fake)
    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {
        "id": "art1", "status": "published", "title": "Artigo",
        "custom_excerpt": "resumo", "url": "https://blog.exemplo.com/a", "plaintext": "corpo"})
    monkeypatch.setenv("XAI_API_KEY", "")
    return bridge, chamadas


def _outcome(rede="linkedin", **extra):
    base = {"publish_target": rede, "publish_content": "versão 1",
            "source_id": "art1", "source_url": "https://blog.exemplo.com/a",
            "publish_media": [], "publish_at": None, "publish_intent": True}
    base.update(extra)
    return base


def test_refazer_abre_nova_aprovacao_no_mesmo_ticket(bridge_com_api):
    bridge, chamadas = bridge_com_api
    r = bridge.refazer(_outcome(), "corta as hashtags", "tkt-1")
    assert r["ok"] is True and r["tentativa"] == 2
    rota, corpo = chamadas[-1]
    assert rota == "/api/approvals"
    assert corpo["ticket_id"] == "tkt-1", "a nova versão pertence ao mesmo trabalho"
    assert corpo["payload"]["title"].startswith("[v2]")


def test_refazer_gera_texto_novo_e_nao_repete_o_reprovado(bridge_com_api):
    bridge, chamadas = bridge_com_api
    bridge.refazer(_outcome(publish_content="TEXTO REPROVADO"), "muda tudo", "tkt-1")
    novo = chamadas[-1][1]["payload"]["outcome"]["publish_content"]
    assert novo != "TEXTO REPROVADO"


def test_refazer_preserva_destino_e_agendamento(bridge_com_api):
    bridge, chamadas = bridge_com_api
    quando = "2026-08-01T12:00:00Z"
    bridge.refazer(_outcome(publish_at=quando), "ajusta", "tkt-1")
    o = chamadas[-1][1]["payload"]["outcome"]
    assert o["publish_target"] == "linkedin" and o["publish_at"] == quando


def test_teto_de_refacoes_evita_laco_infinito(bridge_com_api):
    """Feedback que o modelo não consegue satisfazer viraria geração eterna."""
    bridge, chamadas = bridge_com_api
    antes = len(chamadas)
    r = bridge.refazer(_outcome(), "impossível", "tkt-1", tentativa=bridge.MAX_REFACOES + 1)
    assert r["ok"] is False and "teto" in r["erro"]
    assert len(chamadas) == antes, "não pode abrir aprovação depois do teto"


def test_artigo_de_blog_nao_se_reescreve_sozinho(bridge_com_api):
    """Reescrever o corpo inteiro é trabalho de agente, não de um request —
    fazer em silêncio produziria artigo que ninguém escreveu de fato."""
    bridge, chamadas = bridge_com_api
    antes = len(chamadas)
    r = bridge.refazer(_outcome(rede="blog"), "melhora", "tkt-1")
    assert r["ok"] is False
    assert len(chamadas) == antes


def test_sem_source_id_nao_tem_como_refazer(bridge_com_api):
    bridge, _ = bridge_com_api
    o = _outcome()
    del o["source_id"]
    assert bridge.refazer(o, "ajusta", "tkt-1")["ok"] is False


def test_outcome_do_post_carrega_source_id(monkeypatch):
    """Sem isso o feedback fica registrado e o texto nunca é regenerado."""
    import ghost_social_bridge as bridge

    monkeypatch.setattr(bridge, "buscar_post", lambda _id: {
        "id": "art9", "status": "published", "title": "T", "custom_excerpt": "R",
        "url": "https://e.com/a", "plaintext": "corpo"})
    monkeypatch.setenv("XAI_API_KEY", "")
    r = bridge.distribuir("art9", dry_run=True)
    assert r["redes"], "esperava as redes do blog"


def test_refacao_roda_fora_da_requisicao():
    """Gerar texto passa de um minuto; o bot do Telegram desiste antes. Fazer
    isso dentro do request deixaria o humano num spinner que expira."""
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "approvals.py").read_text(
        encoding="utf-8")
    trecho = fonte.split("def _agendar_refacao")[1]
    assert "threading.Thread" in trecho and "daemon=True" in trecho


# ── credencial da ponte (achado no teste real, 25/07) ────────────────────

def test_env_example_documenta_o_token_da_ponte():
    """APPROVAL_BRIDGE_TOKEN não estava em lugar nenhum: o dashboard recusava
    toda requisição da ponte (fail-closed, correto) e o bot respondia "Bridge
    de aprovação não configurado". Os três botões não faziam nada, e nada disso
    aparecia até alguém apertar. Num deploy de cliente é a mesma armadilha."""
    texto = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "APPROVAL_BRIDGE_TOKEN" in texto
    bloco = texto.split("APPROVAL_BRIDGE_TOKEN")[0][-900:]
    assert "DASHBOARD_API_TOKEN" in bloco, "tem que dizer por que NÃO reutilizar o token de admin"


def test_ponte_recusa_quando_o_token_nao_esta_configurado(monkeypatch):
    """Fail-closed é o comportamento certo — o que faltava era o token, não a
    checagem. Sem token, nenhuma requisição da ponte pode passar."""
    import os as _os

    from routes._helpers import valid_approval_bridge_token

    monkeypatch.delenv("APPROVAL_BRIDGE_TOKEN", raising=False)
    assert valid_approval_bridge_token("Bearer qualquer-coisa") is False

    _os.environ["APPROVAL_BRIDGE_TOKEN"] = "segredo-real"
    try:
        assert valid_approval_bridge_token("Bearer segredo-real") is True
        assert valid_approval_bridge_token("Bearer outro") is False
        assert valid_approval_bridge_token("segredo-real") is False, "exige o prefixo Bearer"
        assert valid_approval_bridge_token(None) is False
    finally:
        _os.environ.pop("APPROVAL_BRIDGE_TOKEN", None)


# ── truncamento do card ──────────────────────────────────────────────────

def test_corte_do_card_nao_parte_palavra_no_meio():
    """Vi "Open sour" no print do Felipe. Cortar cru deixa o humano sem saber
    se o texto acabou assim ou foi truncado — reações opostas ao aprovar."""
    from routes.approvals import _cortar_para_telegram

    texto = ("Primeiro parágrafo com conteúdo real.\n\n"
             + "Segundo parágrafo bem mais longo. " * 60)
    cortado = _cortar_para_telegram(texto, limite=200)
    assert not cortado.replace("[…] texto completo no painel.", "").rstrip().endswith(("sour", "par"))
    assert "[…]" in cortado, "o humano precisa saber que foi cortado"


def test_texto_curto_passa_intacto():
    from routes.approvals import _cortar_para_telegram

    assert _cortar_para_telegram("curto e completo.") == "curto e completo."
    assert "[…]" not in _cortar_para_telegram("curto e completo.")


def test_corte_prefere_fronteira_de_paragrafo():
    from routes.approvals import _cortar_para_telegram

    texto = "Parágrafo um.\n\nParágrafo dois que é muito mais longo " + "x" * 400
    assert _cortar_para_telegram(texto, limite=60).startswith("Parágrafo um.")


def test_env_example_documenta_a_allowlist_de_aprovadores():
    """Segunda metade da ponte, tão obrigatória quanto o token e igualmente
    invisível: sem ela toda decisão volta 403 "not an approver", e isso só
    aparece quando alguém aperta o botão."""
    texto = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "APPROVAL_APPROVER_IDS" in texto
    bloco = texto.split("APPROVAL_APPROVER_IDS")[0][-700:]
    assert "chat" in bloco.lower(), "tem que dizer que é id de usuário, não de chat/grupo"


def test_allowlist_vazia_recusa_qualquer_um(monkeypatch):
    import os as _os

    from routes.approvals import _approver_allowlist

    monkeypatch.delenv("APPROVAL_APPROVER_IDS", raising=False)
    assert _approver_allowlist() == set()

    _os.environ["APPROVAL_APPROVER_IDS"] = "111, 222;333"
    try:
        assert _approver_allowlist() == {"111", "222", "333"}, "aceita vírgula e ponto-e-vírgula"
    finally:
        _os.environ.pop("APPROVAL_APPROVER_IDS", None)


# ── crítica por áudio (falha do primeiro teste real, 25/07) ──────────────

def _fonte_do_bot() -> str:
    return (REPO_ROOT / "scripts" / "telegram_provider_bot.py").read_text(encoding="utf-8")


def _handler_de_ajuste(fonte: str) -> str:
    """O bloco que trata a crítica, delimitado pelo que o abre e o que o fecha.

    Fatiado por `alvo_ajuste` e não por `m_apr` porque o alvo do ajuste deixou de
    vir só do reply amarrado — ver `test_ajuste_sobrevive_a_resposta_solta`.
    """
    return fonte.split("alvo_ajuste = int(m_apr.group(1))")[1].split("if m_tkt:")[0]


def test_ponte_de_ajuste_aceita_audio():
    """No celular, ditar a crítica é o caso NORMAL — mais rápido que digitar
    com o post na tela. O handler só olhava `text`, então o áudio caía no
    agente de conversa e virava uma resposta sem relação com a aprovação.
    Foi exatamente o que aconteceu no primeiro teste real do Felipe."""
    trecho = _handler_de_ajuste(_fonte_do_bot())
    assert "if alvo_ajuste is not None:" in trecho, "não pode exigir texto para entrar no handler"
    assert "message_audio_file_id" in trecho
    assert "handle_audio_message" in trecho


def test_ajuste_por_audio_ecoa_a_transcricao():
    """Numa crítica ditada o humano precisa ver o que o sistema entendeu antes
    de o agente refazer em cima disso."""
    assert "Entendi" in _handler_de_ajuste(_fonte_do_bot())


def test_falha_de_transcricao_nao_vira_silencio():
    trecho = _handler_de_ajuste(_fonte_do_bot())
    assert "Manda por texto" in trecho, "erro tem que dizer o que fazer em seguida"


def test_ponte_de_ticket_tambem_aceita_audio():
    """Mesmo defeito, uma linha abaixo — deixar o idêntico ao lado é pior."""
    fonte = _fonte_do_bot()
    trecho = fonte.split("if m_tkt:")[1].split("audio_file_id = message_audio_file_id")[0]
    assert "handle_audio_message" in trecho
    assert "unblock_ticket" in trecho
