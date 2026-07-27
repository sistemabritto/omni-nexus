"""
tests/heartbeats/test_alerta_com_html_no_texto.py

2026-07-27 — o alerta sumia justamente quando havia o que alertar.

As mensagens de Telegram saem com `parse_mode=HTML`. Vários pontos
interpolavam texto de origem livre sem escapar:

- `heartbeat_runner`: o preview do erro. Traceback carrega `<module>` e
  `<class '...'>`, o Telegram devolvia 400, `urlopen` levantava e
  `notifications._send_telegram` engolia num `except Exception`. Ou seja: o
  alerta de falha desaparecia exatamente quando o erro tinha stack trace.
- `deadline_check`: título de Meta e de Ticket. Uma única Meta chamada
  `A/B de preço < R$100` derrubava o alerta inteiro, com todos os outros
  itens junto.

Run:
    pytest tests/heartbeats/test_alerta_com_html_no_texto.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import notifications  # noqa: E402


# Texto que um humano escreve sem pensar duas vezes, e que quebra HTML.
VENENOS = (
    "A/B de preço < R$100",
    "migrar tickets & goals",
    "<script>alert(1)</script>",
    "comparar a > b no filtro",
)


def _sem_html_cru(texto: str, veneno: str) -> bool:
    """O veneno aparece escapado e o caractere cru não sobrou solto."""
    import html

    return html.escape(veneno, quote=False) in texto and veneno not in texto


# ── heartbeat_runner: o preview do erro ──────────────────────────────────

@pytest.mark.parametrize("veneno", VENENOS)
def test_preview_de_erro_vai_escapado(veneno, monkeypatch):
    import heartbeat_runner as hr

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram", lambda t, **k: enviados.append(t) or True)
    hr.step_alert_on_failure("hb-x", {"status": "fail", "agent": "atlas", "error": veneno})

    assert enviados, "o alerta não chegou a ser montado"
    assert _sem_html_cru(enviados[0], veneno)


def test_traceback_real_nao_derruba_o_alerta(monkeypatch):
    """O caso concreto: `<module>` e `<class '...'>` num traceback."""
    import heartbeat_runner as hr

    traceback = (
        'Traceback (most recent call last):\n'
        '  File "<stdin>", line 1, in <module>\n'
        "TypeError: <class 'NoneType'> is not callable"
    )
    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram", lambda t, **k: enviados.append(t) or True)
    hr.step_alert_on_failure("hb-x", {"status": "fail", "agent": "atlas", "error": traceback})

    assert "<module>" not in enviados[0]
    assert "&lt;module&gt;" in enviados[0]
    # As tags que a gente mesmo escreveu continuam de pé.
    assert "<b>Heartbeat Fail</b>" in enviados[0]


def test_progresso_do_provider_tambem_e_escapado(monkeypatch):
    """A saída do provider é a origem mais livre de todas."""
    import heartbeat_runner as hr

    enviados = []
    monkeypatch.setattr(notifications, "_send_telegram", lambda t, **k: enviados.append(t) or True)
    hr._step_report_success("hb-x", {"status": "success", "agent": "atlas",
                                     "result": "rodei o <diff> e comparei a & b"})

    assert enviados and "<diff>" not in enviados[0]
    assert "&lt;diff&gt;" in enviados[0]


# ── deadline_check: títulos de Meta e Ticket ─────────────────────────────

@pytest.mark.parametrize("veneno", VENENOS)
def test_titulo_de_meta_vencida_vai_escapado(veneno):
    import deadline_check as dc

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    linha = conn.execute("SELECT 1 AS id, ? AS title, '2026-01-01' AS due_date",
                         (veneno,)).fetchall()
    texto = dc._build_alert(linha, [])
    assert _sem_html_cru(texto, veneno)


def test_uma_meta_envenenada_nao_derruba_as_outras():
    """Era o pior da falha: perdia-se o alerta todo, não só aquele item."""
    import deadline_check as dc

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    linhas = conn.execute(
        "SELECT 1 AS id, 'A/B de preço < R$100' AS title, '2026-01-01' AS due_date"
        " UNION ALL SELECT 2, 'Fechar o trimestre', '2026-01-02'").fetchall()
    texto = dc._build_alert(linhas, [])
    assert "Fechar o trimestre" in texto
    assert "&lt; R$100" in texto


# ── o log tem de dizer o motivo certo ────────────────────────────────────

def test_sem_credencial_e_recusa_do_telegram_logam_diferente(monkeypatch, caplog):
    """`send_telegram_alert` devolve False nos dois casos.

    Enquanto o log afirmava "Telegram not configured", quem investigava ia
    conferir o .env, achava tudo certo e descartava a pista.
    """
    import logging
    import urllib.error

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with caplog.at_level(logging.WARNING):
        assert notifications._send_telegram("oi") is False
    assert "ausentes" in caplog.text

    caplog.clear()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    def _recusa(*a, **k):
        raise urllib.error.HTTPError("url", 400, "Bad Request", {}, None)

    monkeypatch.setattr(notifications.urllib.request, "urlopen", _recusa)
    with caplog.at_level(logging.WARNING):
        assert notifications._send_telegram("oi") is False
    assert "recusou" in caplog.text
    assert "ausentes" not in caplog.text
