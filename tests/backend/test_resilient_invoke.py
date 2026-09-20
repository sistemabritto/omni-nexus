"""Motor de resiliência (resilient_invoke / _is_retryable_failure).

Cobre: classificação de falha transitória vs fatal, retry em "busy" e timeout,
backoff exponencial (busy usa o menor), orçamentos por tempo e por nº de
tentativas, on_status chamado a cada nova tentativa, e compatibilidade de
chamada única (sem budget → idêntico a invoke_with_fallback).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "dashboard" / "backend"))

import provider_fallback as pf  # noqa: E402


# ── Classificação da falha ────────────────────────────────────────────────────

@pytest.mark.parametrize("resultado", [
    {"status": "busy", "error": "workspace busy — another agentic run held the lock for 120.0s"},
    {"status": "fail", "error": "The read operation timed out"},
    {"status": "timeout", "error": "Killed after 280s timeout"},
    {"status": "fail", "error": "[Errno 101] Network is unreachable"},
    {"status": "fail", "error": "{'status':529,'detail':'Service temporarily overloaded'}"},
    {"status": "fail", "error": "Connection reset by peer"},
])
def test_is_retryable_transitории(resultado):
    assert pf._is_retryable_failure(resultado) is True


@pytest.mark.parametrize("resultado", [
    {"status": "success", "output": "ok"},
    {"status": "fail", "error": "401 Unauthorized — invalid_api_key"},
    {"status": "fail", "error": "Authentication failed (status 403)"},
    {"status": "fail", "error": "Some unknown content error with no transient hint"},
])
def test_is_retryable_fatais(resultado):
    assert pf._is_retryable_failure(resultado) is False


# ── Retry em busy / timeout com backoff ───────────────────────────────────────

def _fake_invoke(results):
    """Monta um invoke_with_fallback que devolve a lista `results` em ordem."""
    calls = {"n": 0}

    def fake(prompt, **kwargs):
        i = min(calls["n"], len(results) - 1)
        calls["n"] += 1
        return results[i]
    return fake, calls


def test_busy_retrya_ate_sucesso(monkeypatch):
    ok = {"status": "success", "output": '{"result":"oi"}', "provider_id": "omnirouter"}
    busy = {"status": "busy", "error": "workspace busy — another agentic run held the lock for 120.0s"}
    fake, calls = _fake_invoke([busy, busy, ok])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    slept = []
    monkeypatch.setattr(pf.time, "sleep", lambda s: slept.append(s))

    out = pf.resilient_invoke(
        "prompt", retry_budget_seconds=600, backoff_base_seconds=20, backoff_cap_seconds=180,
    )
    assert out["status"] == "success"
    assert calls["n"] == 3
    # busy usa a menor espera (base) nas duas quedas
    assert slept == [20, 20]


def test_timeout_backoff_exponencial(monkeypatch):
    to = {"status": "timeout", "error": "Killed after 280s timeout | provider said: …"}
    ok = {"status": "success", "output": '{"result":"ok"}'}
    fake, calls = _fake_invoke([to, to, to, ok])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    slept = []
    monkeypatch.setattr(pf.time, "sleep", lambda s: slept.append(s))

    out = pf.resilient_invoke(
        "prompt", retry_budget_seconds=9999, backoff_base_seconds=20, backoff_cap_seconds=180,
    )
    assert out["status"] == "success" and calls["n"] == 4
    # 20, 40, 80 (exponencial)
    assert slept == [20, 40, 80]


def test_backoff_respeita_cap(monkeypatch):
    to = {"status": "timeout", "error": "timed out"}
    ok = {"status": "success", "output": ""}
    fake, _ = _fake_invoke([to] * 5 + [ok])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    slept = []
    monkeypatch.setattr(pf.time, "sleep", lambda s: slept.append(s))

    pf.resilient_invoke("p", retry_budget_seconds=9999,
                        backoff_base_seconds=20, backoff_cap_seconds=50)
    # 20,40,50(cap),50(cap),50(cap)
    assert slept == [20, 40, 50, 50, 50]


def test_falha_fatal_nao_retrya(monkeypatch):
    auth = {"status": "fail", "error": "401 Unauthorized"}
    fake, calls = _fake_invoke([auth])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)

    out = pf.resilient_invoke("p", retry_budget_seconds=600)
    assert out["status"] == "fail"
    assert calls["n"] == 1  # devolveu direto, sem retry


def test_budget_por_tentativas(monkeypatch):
    busy = {"status": "busy", "error": "held the lock"}
    fake, calls = _fake_invoke([busy])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    slept = []
    monkeypatch.setattr(pf.time, "sleep", lambda s: slept.append(s))

    out = pf.resilient_invoke("p", max_retries=2, backoff_base_seconds=5)
    assert out["status"] == "busy"
    assert calls["n"] == 3  # 1ª chamada + 2 retries extras


def test_on_status_chamado_a_cada_retry(monkeypatch):
    busy = {"status": "busy", "error": "held the lock for 120s"}
    fake, _ = _fake_invoke([busy])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    monkeypatch.setattr(pf.time, "sleep", lambda s: None)
    status_calls = []

    pf.resilient_invoke(
        "p", max_retries=3, backoff_base_seconds=1,
        on_status=lambda n, st, det: status_calls.append((n, st)),
    )
    # teto 3 tentativas extras → on_status a cada retry (próximas tentativas 2,3,4)
    assert [c[0] for c in status_calls] == [2, 3, 4]
    assert all(c[1] == "busy" for c in status_calls)


def test_comportamento_compativel_sem_budget(monkeypatch):
    busy = {"status": "busy", "error": "held the lock"}
    fake, calls = _fake_invoke([busy])
    monkeypatch.setattr(pf, "invoke_with_fallback", fake)
    monkeypatch.setattr(pf.time, "sleep", lambda s: pytest.fail("não deve dormir sem budget"))

    out = pf.resilient_invoke("p")
    assert out["status"] == "busy" and calls["n"] == 1  # idêntico a chamada única


# ── streaming: on_stdout_line chega em tempo real ─────────────────────────────

def test_on_stdout_line_propagado_no_attempt(monkeypatch):
    seen = []
    monkeypatch.setattr(pf, "_invoke_cli_run", lambda cmd, run_env, timeout_seconds,
                        workspace, output_mode="envelope", stdin_input=None, on_stdout_line=None:
                        (on_stdout_line('{"type":"text","part":{"text":"parcial"}}'),
                         on_stdout_line(""),
                         {"status": "success", "output": "{}", "error": None, "duration_ms": 1,
                          "tokens_in": None, "tokens_out": None, "cost_usd": None})[2])
    monkeypatch.setattr(pf.shutil, "which", lambda b: "/bin/sh")

    res = pf._invoke_cli(
        cli_command="claude", prompt="x", max_turns=3, timeout_seconds=5,
        provider_id="omnirouter", model="m", on_stdout_line=lambda l: seen.append(l),
    )
    assert res["status"] == "success"
    assert seen == ['{"type":"text","part":{"text":"parcial"}}', ""]
