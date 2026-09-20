"""Janela de indisponibilidade por cota no provider_fallback.

Cobre: parse da data/hora de reset na resposta (7 formatos), janelas declaradas
(config/availability.yaml), auto-detect gravado na resposta (availability.auto.json),
e o skip real no loop de attempts (provider em janela é pulado e o combo gira).
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "dashboard" / "backend"))

import provider_fallback as pf  # noqa: E402


# ── Parse da data/hora de reset ────────────────────────────────────────────────

@pytest.mark.parametrize("texto,espera_horas", [
    ("You've hit your quota. It resets on 22 September 2026 at 00:00 UTC.", (17, 52)),
    ("Your monthly usage limit resets in 2 days.", (46, 50)),
    ("quota resets 2026-09-22T00:00:00Z", (15, 52)),
    ("Quota reset on 22/09/2026 00:00", (15, 52)),
    ("Your weekly limit resets in 36 hours.", (34, 38)),
    ("insufficient credits. Plan limit resets on Sep 21, 2026", (15, 40)),
    ("monthly limit reached — becomes available again on 2026-09-22", (17, 52)),
])
def test_parse_reset_date_formatos(texto, espera_horas):
    dt = pf._parse_reset_date(texto)
    assert dt is not None, f"não extraiu data de: {texto!r}"
    hours = (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    lo, hi = espera_horas
    assert lo <= hours <= hi, f"{hours:.1f}h fora de [{lo},{hi}] para {texto!r}"


@pytest.mark.parametrize("texto", [
    "Failed to authenticate. API Error: Authentication failed (status 401).",
    "Something went wrong",
    "",
])
def test_parse_reset_date_sem_data(texto):
    assert pf._parse_reset_date(texto) is None


def test_gatilho_reset_lead_somente_mensagens_de_cota():
    assert pf._RE_RESET_LEAD.search("Your quota resets on Sep 22")
    assert pf._RE_RESET_LEAD.search("monthly usage limit hit")
    assert pf._RE_RESET_LEAD.search("out of credit balance")
    assert not pf._RE_RESET_LEAD.search("olá, aqui está o relatório")


# ── Janelas declaradas ──────────────────────────────────────────────────────────

def test_windows_lidos_do_yaml(tmp_path, monkeypatch):
    decl = tmp_path / "availability.yaml"
    decl.write_text(
        "enabled: true\nproviders:\n"
        '  codex_auth:\n    until: "2026-09-22 00:00"\n'
        '  anthropic:\n    until: "2026-09-21 22:00"\n', encoding="utf-8")
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", decl)
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", tmp_path / "auto.json")

    windows = pf._availability_windows()
    now = datetime.now(timezone.utc)
    assert set(windows) == {"codex_auth", "anthropic"}
    # Codex ~2 dias, Claude ~1 dia (declara em BRT)
    assert windows["codex_auth"] > windows["anthropic"]
    assert all(ts > now.timestamp() for ts in windows.values())


def test_window_expirada_nao_entra(monkeypatch, tmp_path):
    decl = tmp_path / "availability.yaml"
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).astimezone(pf.BRT).strftime("%Y-%m-%d %H:%M")
    decl.write_text(f'providers:\n  codex_auth:\n    until: "{past}"\n', encoding="utf-8")
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", decl)
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", tmp_path / "auto.json")
    assert pf._availability_windows() == {}


# ── Auto-detect: grava na resposta ──────────────────────────────────────────────

def test_record_provider_unavailable_grava(monkeypatch, tmp_path):
    auto = tmp_path / "auto.json"
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", auto)
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", tmp_path / "declarado.yaml")
    monkeypatch.setattr(pf, "AVAILABILITY_TTL_SECONDS", 3 * 24 * 3600)

    pf._record_provider_unavailable("codex_auth", "You've hit your quota. It resets on 22 September 2026.")
    import json
    data = json.loads(auto.read_text(encoding="utf-8"))
    assert "codex_auth" in data["windows"]
    assert data["windows"]["codex_auth"]["source"] == "auto"
    exp = datetime.fromisoformat(data["windows"]["codex_auth"]["expires_at"])
    assert (exp - datetime.now(timezone.utc)).total_seconds() > 0


def test_record_ignora_sem_data_de_reset(monkeypatch, tmp_path):
    auto = tmp_path / "auto.json"
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", auto)
    pf._record_provider_unavailable("omnirouter", "Killed after 99s timeout")
    assert not auto.exists() or json.loads(auto.read_text())["windows"].get("omnirouter") is None


def test_window_auto_prevalece_se_mais_longa(monkeypatch, tmp_path):
    decl = tmp_path / "availability.yaml"
    decl.write_text('providers:\n  codex_auth:\n    until: "2026-09-22 00:00"\n', encoding="utf-8")
    auto = tmp_path / "auto.json"
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    auto.write_text(json.dumps({"windows": {"codex_auth": {"expires_at": future}}}), encoding="utf-8")
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", decl)
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", auto)
    w = pf._availability_windows()
    assert w["codex_auth"] > datetime.fromisoformat(future).timestamp() - 60


# ── Skip real no loop de attempts ───────────────────────────────────────────────

def test_combo_pula_providers_indisponiveis(monkeypatch, tmp_path, capsys):
    """CX-WORKHORSE = [codex_auth, omnirouter, anthropic]; com ambos em janela,
    a tentativa deve ir direto ao omnirouter (Drael)."""
    decl = tmp_path / "availability.yaml"
    decl.write_text(
        "enabled: true\nproviders:\n"
        '  codex_auth:\n    until: "2026-09-22 00:00"\n'
        '  anthropic:\n    until: "2026-09-21 22:00"\n', encoding="utf-8")
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", decl)
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", tmp_path / "auto.json")

    seen = []

    def fake_run(self):
        seen.append(self.provider_id)
        return {"status": "fail", "error": "x", "output": ""}

    monkeypatch.setattr(pf.FallbackAttempt, "run", fake_run)
    pf.clear_all_cooldowns()
    eng = pf.FallbackEngine()
    for a in eng.attempts("ping", timeout_seconds=600, routing_key="reels-copilot"):
        a.run()

    assert seen, "nenhuma tentativa foi feita"
    assert seen[0] == "omnirouter", f"esperava começar em omnirouter, foi {seen[0]!r}"
    assert "codex_auth" not in seen
    assert "anthropic" not in seen
    out = capsys.readouterr().out
    assert "sem cota" in out, "deveria logar o pulo do provider"


def test_combo_sem_janela_mantem_ordem_original(monkeypatch, tmp_path):
    """Sem availability.yaml, o combo CX-WORKHORSE segue codex → drael → claude."""
    monkeypatch.setattr(pf, "AVAILABILITY_DECL", tmp_path / "inexistente.yaml")
    monkeypatch.setattr(pf, "AVAILABILITY_AUTO", tmp_path / "inexistente.json")

    seen = []

    def fake_run(self):
        seen.append(self.provider_id)
        if len(seen) >= 1:
            return {"status": "success", "output": "ok"}
        return {"status": "fail", "error": "x", "output": ""}

    monkeypatch.setattr(pf.FallbackAttempt, "run", fake_run)
    pf.clear_all_cooldowns()
    eng = pf.FallbackEngine()
    res = None
    for a in eng.attempts("ping", timeout_seconds=600, routing_key="reels-copilot"):
        res = a.run()
        if res.get("status") == "success":
            break
    assert res and res["status"] == "success"
    assert seen[0] == "codex_auth"
