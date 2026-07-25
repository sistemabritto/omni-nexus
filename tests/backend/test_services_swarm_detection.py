"""
tests/backend/test_services_swarm_detection.py

A página /scheduler mostrava TODOS os serviços como "Stopped" na VPS enquanto
eles rodavam normalmente (print do Felipe, 25/07/2026).

Causa: a detecção usava `screen -list`, que só existe no modelo local de uma
máquina só. Em Swarm cada serviço é um container próprio e o binário `screen`
nem está instalado na imagem — a checagem falhava sempre e virava "Stopped".

É o pior tipo de erro de painel: mentir com confiança. Um indicador que não sabe
tem que dizer "não sei", não "está parado".

Run:
    pytest tests/backend/test_services_swarm_detection.py -v
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routes import services as S  # noqa: E402


# ── detecção de topologia ────────────────────────────────────────────────

def test_env_explicito_forca_modo_container(monkeypatch):
    monkeypatch.setenv("EVONEXUS_DEPLOY_MODE", "swarm")
    assert S._container_mode() is True


def test_sem_screen_mais_marcador_de_container(monkeypatch):
    """Na imagem do dashboard o `screen` não existe e /workspace existe."""
    monkeypatch.delenv("EVONEXUS_DEPLOY_MODE", raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda _: None)
    monkeypatch.setattr(S.Path, "is_dir", lambda self: str(self) == "/workspace")
    assert S._container_mode() is True


def test_sem_screen_e_sem_marcador_continua_local(monkeypatch):
    """Ausência de `screen` numa máquina de dev não implica container — o
    palpite errado aqui reintroduziria o bug ao contrário."""
    monkeypatch.delenv("EVONEXUS_DEPLOY_MODE", raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda _: None)
    monkeypatch.setattr(S.Path, "exists", lambda self: False)
    monkeypatch.setattr(S.Path, "is_dir", lambda self: False)
    assert S._container_mode() is False


def test_com_screen_instalado_e_local(monkeypatch):
    monkeypatch.delenv("EVONEXUS_DEPLOY_MODE", raising=False)
    monkeypatch.setattr(S.shutil, "which", lambda _: "/usr/bin/screen")
    assert S._container_mode() is False


# ── evidência de log ─────────────────────────────────────────────────────

def test_log_recente_conta_como_rodando(monkeypatch):
    monkeypatch.setattr(S, "_newest_mtime", lambda *a: time.time() - 120)
    r = S._from_log_evidence("Scheduler", "x")
    assert r["running"] is True and r["status"] == "running"


def test_sem_log_nenhum_e_unknown_nao_stopped(monkeypatch):
    """'Não sei' e 'está parado' são coisas diferentes — foi a confusão do bug."""
    monkeypatch.setattr(S, "_newest_mtime", lambda *a: None)
    r = S._from_log_evidence("Telegram", "x")
    assert r["status"] == "unknown"
    assert r["running"] is not False


def test_log_velho_e_unknown_nao_stopped(monkeypatch):
    monkeypatch.setattr(S, "_newest_mtime", lambda *a: time.time() - 30 * 3600)
    r = S._from_log_evidence("Telegram", "x")
    assert r["status"] == "unknown"
    assert r["running"] is not False


# ── contrato da resposta ─────────────────────────────────────────────────

@pytest.fixture
def app_cliente():
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(S.bp)
    return app.test_client()


def test_resposta_continua_sendo_lista_em_swarm(app_cliente, monkeypatch):
    """Mudar a forma da resposta conforme o ambiente quebraria o frontend
    exatamente no Swarm, que é onde a correção importa."""
    monkeypatch.setattr(S, "_container_mode", lambda: True)
    body = app_cliente.get("/api/services").get_json()
    assert isinstance(body, list)
    assert {s["id"] for s in body} >= {"scheduler", "telegram", "dashboard"}


def test_dashboard_nunca_aparece_parado(app_cliente, monkeypatch):
    """Se a rota respondeu, o dashboard está rodando — perguntar ao `ps` era teatro."""
    monkeypatch.setattr(S, "_container_mode", lambda: True)
    body = app_cliente.get("/api/services").get_json()
    dash = next(s for s in body if s["id"] == "dashboard")
    assert dash["running"] is True


def test_em_swarm_nao_oferece_comando_make_que_nao_funciona(app_cliente, monkeypatch):
    monkeypatch.setattr(S, "_container_mode", lambda: True)
    body = app_cliente.get("/api/services").get_json()
    for s in body:
        if s.get("category") == "channel":
            assert "command" not in s, f"{s['id']} não deve oferecer botão inoperante"
            assert s.get("managed_by") == "swarm"


def test_em_local_mantem_o_comando(app_cliente, monkeypatch):
    monkeypatch.setattr(S, "_container_mode", lambda: False)
    body = app_cliente.get("/api/services").get_json()
    telegram = next(s for s in body if s["id"] == "telegram")
    assert telegram.get("command") == "make telegram"


def test_todo_servico_declara_status_e_modo(app_cliente, monkeypatch):
    monkeypatch.setattr(S, "_container_mode", lambda: True)
    for s in app_cliente.get("/api/services").get_json():
        assert s.get("status") in ("running", "stopped", "unknown")
        assert s.get("deploy_mode") == "swarm"
