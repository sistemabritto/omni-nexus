"""
tests/backend/test_whatsapp_notifications.py

Panorama 2026-07-17, item 3 — notifications.send_whatsapp usava
`/message/sendText/{instance}` com EVOLUTION_GO_KEY (a chave admin). Essa
rota nunca existiu nesta API (404 confirmado) e a chave admin devolve 401
"not authorized" em qualquer endpoint `/send/*` — só o token de uma
instância específica autentica ali. Reescrito em 28/07/2026 depois de
confirmar ao vivo: `POST /send/text` com EVOLUTION_GO_SEND_TOKEN devolve 200
e a mensagem chega de verdade. Ver notifications.py::send_whatsapp para o
histórico completo (era a terceira causa empilhada: rota errada, chave
errada, e por fim o User-Agent padrão do urllib também levava 403).

Run:
    cd /path/to/workspace && pytest tests/backend/test_whatsapp_notifications.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import notifications  # noqa: E402


@pytest.fixture(autouse=True)
def _evolution_go_env(monkeypatch):
    monkeypatch.setenv("EVOLUTION_GO_URL", "https://evo.example.com")
    monkeypatch.setenv("EVOLUTION_GO_SEND_TOKEN", "test-instance-token")
    monkeypatch.delenv("EVOLUTION_GO_KEY", raising=False)


def _mock_response():
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_send_whatsapp_usa_a_rota_send_text_sem_instancia_no_path():
    with patch("urllib.request.urlopen", return_value=_mock_response()) as mock_urlopen:
        ok = notifications.send_whatsapp("oi", "5511999999999")
    assert ok is True
    request_obj = mock_urlopen.call_args[0][0]
    assert request_obj.full_url == "https://evo.example.com/send/text"


def test_send_whatsapp_autentica_com_o_send_token_nao_com_a_chave_admin(monkeypatch):
    monkeypatch.setenv("EVOLUTION_GO_KEY", "chave-admin-nunca-deveria-ser-usada")
    with patch("urllib.request.urlopen", return_value=_mock_response()) as mock_urlopen:
        notifications.send_whatsapp("oi", "5511999999999")
    request_obj = mock_urlopen.call_args[0][0]
    assert request_obj.get_header("Apikey") == "test-instance-token"


def test_send_whatsapp_manda_user_agent_de_navegador():
    """Sem isso o gateway devolve 403 pro UA padrão "Python-urllib/x.y" —
    confirmado ao vivo contra go.workflowapi.com.br em 28/07/2026."""
    with patch("urllib.request.urlopen", return_value=_mock_response()) as mock_urlopen:
        notifications.send_whatsapp("oi", "5511999999999")
    request_obj = mock_urlopen.call_args[0][0]
    assert "python-urllib" not in (request_obj.get_header("User-agent") or "").lower()


def test_send_whatsapp_returns_false_without_credentials(monkeypatch):
    monkeypatch.delenv("EVOLUTION_GO_URL", raising=False)
    monkeypatch.delenv("EVOLUTION_GO_SEND_TOKEN", raising=False)
    assert notifications.send_whatsapp("oi", "5511999999999") is False
