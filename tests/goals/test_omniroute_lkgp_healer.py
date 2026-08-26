"""
tests/goals/test_omniroute_lkgp_healer.py

Self-healing do cache LKGP do OmniRoute (25/08/2026).

O OmniRoute cacheia "último provider que funcionou" por combo. Quando esse
provider se aposenta (410 Gone), o cache não se auto-invalida — toda
chamada nova paga a taxa de tentar o morto primeiro antes de ciclar a pool.
`z-ai/glm-5.2` ficou preso assim depois de aposentar em 21/08/2026 e travou
respostas do Magneto/Hermes. `DELETE /api/settings/lkgp-cache` resolveu na
hora; esta rotina existe para nunca depender de alguém notar isso na mão.

O que este arquivo trava:
  1. erro permanente (410/404, ou mensagem de fim de vida) dispara a limpeza
  2. erro transitório (429, 5xx) NUNCA dispara — destruiria a utilidade do
     próprio cache durante um pico normal de uso
  3. o mesmo incidente não gera limpeza nem alerta repetido a cada tick
  4. reincidência real (mesmo erro depois da janela) alerta uma vez, escalado

Run:
    pytest tests/goals/test_omniroute_lkgp_healer.py -v
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ADWs" / "routines"))
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))

import omniroute_lkgp_healer as healer  # noqa: E402


# ── 1. permanente vs transitório — a linha que não pode errar ────────────

@pytest.mark.parametrize("codigo,mensagem,esperado", [
    ("410", "Gone", True),
    ("410.0", "the model has reached its end of life", True),
    ("404", "not found", True),
    (None, "This model is deprecated, use X instead", True),
    (None, "The model has been decommissioned", True),
    # transitório — nunca dispara limpeza
    ("429", "rate limit exceeded", False),
    ("500", "internal server error", False),
    ("502", "bad gateway", False),
    ("503", "service unavailable, try again", False),
    (None, "", False),
    (None, None, False),
])
def test_erro_e_permanente(codigo, mensagem, esperado):
    assert healer.erro_e_permanente(codigo, mensagem) is esperado


# ── 2. main(): não faz nada sem senha configurada ────────────────────────

def test_main_sem_senha_nao_falha_nem_chama_omniroute(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_ADMIN_PASSWORD", raising=False)
    with patch.object(healer, "login") as mock_login:
        assert healer.main() == 0
        mock_login.assert_not_called()


# ── 3. main(): erro transitório nunca limpa ──────────────────────────────

def test_main_ignora_erro_transitorio(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIROUTE_ADMIN_PASSWORD", "senha")
    monkeypatch.setattr(healer, "STATE_PATH", tmp_path / "state.json")
    conexoes = [{"provider": "nvidia", "testStatus": "unavailable",
                 "errorCode": "429", "lastError": "rate limit exceeded"}]
    with patch.object(healer, "login", return_value="tok"), \
         patch.object(healer, "_http") as mock_http:
        mock_http.return_value = {"connections": conexoes}
        assert healer.main() == 0
    # só a chamada de GET /api/providers — nunca um DELETE
    calls = [c.args[0] for c in mock_http.call_args_list]
    assert "DELETE" not in calls


# ── 4. main(): erro permanente limpa e grava estado ──────────────────────

def test_main_limpa_erro_permanente_e_grava_estado(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIROUTE_ADMIN_PASSWORD", "senha")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(healer, "STATE_PATH", state_path)
    conexoes = [{"provider": "nvidia", "testStatus": "unavailable",
                 "errorCode": "410", "lastError": "model has reached its end of life"}]

    def fake_http(method, url, **kwargs):
        if method == "GET":
            return {"connections": conexoes}
        if method == "DELETE":
            return {"cleared": True}
        raise AssertionError(f"método inesperado: {method}")

    with patch.object(healer, "login", return_value="tok"), \
         patch.object(healer, "_http", side_effect=fake_http), \
         patch.object(healer, "notify_limpeza") as mock_notify:
        assert healer.main() == 0
        mock_notify.assert_called_once()

    estado = json.loads(state_path.read_text())
    assert len(estado) == 1
    (entrada,) = estado.values()
    assert "limpo_em" in entrada


# ── 5. mesmo incidente não repete limpeza nem alerta a cada tick ─────────

def test_main_nao_repete_limpeza_para_o_mesmo_incidente(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIROUTE_ADMIN_PASSWORD", "senha")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(healer, "STATE_PATH", state_path)
    conexao = {"provider": "nvidia", "testStatus": "unavailable",
               "errorCode": "410", "lastError": "model has reached its end of life"}
    assinatura = f"{conexao['provider']}:{conexao['errorCode']}:{conexao['lastError'][:120]}"
    # já tratado agora mesmo — bem dentro da janela de reincidência
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        assinatura: {"limpo_em": time.time(), "reincidencia_avisada": False}
    }))

    def fake_http(method, url, **kwargs):
        if method == "GET":
            return {"connections": [conexao]}
        raise AssertionError("não deveria chamar DELETE de novo tão cedo")

    with patch.object(healer, "login", return_value="tok"), \
         patch.object(healer, "_http", side_effect=fake_http), \
         patch.object(healer, "notify_reincidencia") as mock_reinc:
        assert healer.main() == 0
        # ainda dentro da janela, sem reincidência de verdade — não alerta
        mock_reinc.assert_not_called()


# ── 6. reincidência real (fora da janela) alerta uma vez, não em loop ────

def test_main_alerta_reincidencia_uma_vez_so(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIROUTE_ADMIN_PASSWORD", "senha")
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(healer, "STATE_PATH", state_path)
    healer.REINCIDENCIA_HORAS = 6  # garante o valor padrão neste teste
    conexao = {"provider": "nvidia", "testStatus": "unavailable",
               "errorCode": "410", "lastError": "model has reached its end of life"}
    assinatura = f"{conexao['provider']}:{conexao['errorCode']}:{conexao['lastError'][:120]}"
    fora_da_janela = time.time() - 7 * 3600  # 7h atrás, janela é 6h
    state_path.write_text(json.dumps({
        assinatura: {"limpo_em": fora_da_janela}
    }))

    def fake_http(method, url, **kwargs):
        if method == "GET":
            return {"connections": [conexao]}
        if method == "DELETE":
            # self-healing não desiste na reincidência: tenta limpar de novo
            return {"cleared": True}
        raise AssertionError(f"método inesperado: {method}")

    with patch.object(healer, "login", return_value="tok"), \
         patch.object(healer, "_http", side_effect=fake_http), \
         patch.object(healer, "notify_reincidencia") as mock_reinc:
        assert healer.main() == 0
        mock_reinc.assert_called_once()

    # rodar de nogo imediatamente depois: o clear da reincidência já
    # atualizou "limpo_em" para agora — a próxima chamada cai dentro da
    # janela de novo, sem alertar uma segunda vez seguida.
    with patch.object(healer, "login", return_value="tok"), \
         patch.object(healer, "_http", side_effect=fake_http), \
         patch.object(healer, "notify_reincidencia") as mock_reinc2:
        assert healer.main() == 0
        mock_reinc2.assert_not_called()


# ── 7. OmniRoute fora do ar não derruba a rotina ─────────────────────────

def test_main_sobrevive_a_omniroute_fora_do_ar(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIROUTE_ADMIN_PASSWORD", "senha")
    monkeypatch.setattr(healer, "STATE_PATH", tmp_path / "state.json")
    with patch.object(healer, "login", side_effect=RuntimeError("login no OmniRoute falhou")):
        assert healer.main() == 0
