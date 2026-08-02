"""
tests/goals/test_approvals_publish_preview.py

A página /approvals mostrava `payload["body"]` — resumo truncado escrito pelo
agente. O que publica é `payload["outcome"]["publish_content"]` +
`publish_media`, outro par de campos. Aprovar lendo o resumo é aprovar uma
coisa e publicar outra: exatamente o problema de confiança que o gate existe
para evitar. O card do Telegram já mostrava o conteúdo real; o dashboard não.

Sem `media` na resposta a imagem não tem como ser renderizada, e validar
imagem lendo URL não funciona — é preciso ver.

Run:
    pytest tests/goals/test_approvals_publish_preview.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routes.approvals import _formatar_publicacao, _render_publish_preview  # noqa: E402


CONTEUDO = "Texto exato que vai ao ar, sem truncar."
IMAGEM = "https://blog.sistemabritto.com.br/content/images/capa.png"


def _payload(**extra):
    outcome = {
        "publish_target": "instagram",
        "publish_content": CONTEUDO,
        "publish_media": [IMAGEM],
        "publish_at": "2026-07-26T14:00:00Z",
    }
    outcome.update(extra)
    return {"title": "Publicar em instagram: artigo", "body": "resumo curto", "outcome": outcome}


def test_expoe_o_conteudo_real_e_nao_o_resumo():
    p = _render_publish_preview("publish", _payload())
    assert p["content"] == CONTEUDO
    assert p["content"] != "resumo curto"


def test_expoe_a_midia_para_a_pagina_renderizar():
    assert _render_publish_preview("publish", _payload())["media"] == [IMAGEM]


def test_expoe_destino_e_horario():
    p = _render_publish_preview("publish", _payload())
    assert p["target"] == "instagram"
    assert p["publish_at"] == "2026-07-26T14:00:00Z"


def test_publicacao_imediata_nao_inventa_horario():
    p = _render_publish_preview("publish", _payload(publish_at=None))
    assert p["publish_at"] is None


def test_sem_midia_devolve_lista_vazia():
    assert _render_publish_preview("publish", _payload(publish_media=[]))["media"] == []


def test_midia_malformada_e_descartada_em_vez_de_quebrar_a_pagina():
    p = _render_publish_preview("publish", _payload(publish_media=[IMAGEM, 42, None, {"u": "x"}]))
    assert p["media"] == [IMAGEM]


def test_outros_gates_nao_ganham_preview_de_publicacao():
    for gate in ("decomposition", "project_suggestion", "goal_suggestion"):
        assert _render_publish_preview(gate, _payload()) is None


def test_publish_sem_outcome_nao_quebra():
    assert _render_publish_preview("publish", {"title": "x", "body": "y"}) is None


def test_outcome_de_tipo_errado_nao_quebra():
    assert _render_publish_preview("publish", {"outcome": "texto solto"}) is None


def test_conteudo_vazio_e_reportado_como_vazio_nao_como_resumo():
    """Fail-loud: a página precisa poder dizer 'nada seria publicado'. Cair no
    resumo aqui esconderia um outcome quebrado atrás de um texto plausível."""
    p = _render_publish_preview("publish", _payload(publish_content=""))
    assert p["content"] == ""


def test_dict_de_aprovacao_inclui_o_bloco_publish():
    """Contrato com o frontend: o campo tem que existir sempre, mesmo nulo."""
    import json
    from types import SimpleNamespace

    from routes.approvals import _approval_to_dict

    row = SimpleNamespace(
        id=1, gate_type="publish", status="pending", agent="pixel-social-media",
        ticket_id=None, goal_id=None, mission_id=None, project_id=None,
        payload=json.dumps(_payload()), created_at="2026-07-25T12:00:00Z",
        expires_at="2026-07-26T12:00:00Z", decided_at=None, decided_by=None,
    )
    d = _approval_to_dict(row)
    assert d["publish"]["content"] == CONTEUDO
    assert d["publish"]["media"] == [IMAGEM]

    row.gate_type = "decomposition"
    assert "publish" in _approval_to_dict(row)
    assert _approval_to_dict(row)["publish"] is None


# ── links de validação (pedido do Felipe, 25/07) ─────────────────────────

def test_link_do_artigo_acompanha_a_aprovacao():
    """Post da rede e artigo são artefatos diferentes; validar um não valida o
    outro. Em draft o Ghost devolve a URL de preview, que abre sem login."""
    p = _render_publish_preview("publish", _payload(
        source_url="https://blog.sistemabritto.com.br/p/8f2c-uuid/"))
    assert p["source_url"] == "https://blog.sistemabritto.com.br/p/8f2c-uuid/"


def test_sem_link_o_campo_vem_nulo_e_a_ui_omite():
    assert _render_publish_preview("publish", _payload())["source_url"] is None


def test_link_que_nao_e_http_e_recusado():
    """Impede javascript: e afins virarem href renderizado na página."""
    for lixo in ("javascript:alert(1)", "/relativo", 42, None):
        assert _render_publish_preview("publish", _payload(source_url=lixo))["source_url"] is None


def test_base_publica_prefere_env_ao_host_interno():
    """request.host_url devolve o host interno atrás do Traefik; um link para
    http://evonexus-dashboard:8080 não abre no celular de ninguém."""
    import os

    from routes.approvals import _base_publica

    anterior = {k: os.environ.get(k) for k in ("NEXUS_PUBLIC_URL", "NGROK_URL")}
    try:
        os.environ.pop("NEXUS_PUBLIC_URL", None)
        os.environ["NGROK_URL"] = "https://nexus.workflowapi.com.br/"
        assert _base_publica() == "https://nexus.workflowapi.com.br"

        os.environ["NEXUS_PUBLIC_URL"] = "https://outro.exemplo.com"
        assert _base_publica() == "https://outro.exemplo.com", "o nome novo vence"

        os.environ["NEXUS_PUBLIC_URL"] = "evonexus-dashboard:8080"
        assert _base_publica() == "https://nexus.workflowapi.com.br", "valor sem http é ignorado"
    finally:
        for k, v in anterior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── horário da publicação no card ───────────────────────────────────────────

def test_formatar_publicacao_iso_utc_vira_brt():
    """`2026-08-02T15:00:00Z` é 12:00 de Brasília (UTC-3 fixo)."""
    assert _formatar_publicacao("2026-08-02T15:00:00Z") == "02/08 12:00"


def test_formatar_publicacao_com_offset_vira_brt():
    assert _formatar_publicacao("2026-08-02T18:30:00+00:00") == "02/08 15:30"


def test_formatar_publicacao_vazio_ou_invalido():
    assert _formatar_publicacao(None) == ""
    assert _formatar_publicacao("") == ""
    assert _formatar_publicacao("nem-iso") == ""
