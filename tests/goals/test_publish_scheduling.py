"""
tests/goals/test_publish_scheduling.py

Objetivo 1 (2026-07-25) — Postiz passa a ser o intermediário oficial de
AGENDAMENTO, não só de publicação imediata.

Antes desta mudança `_run_publish_action` só sabia chamar
`create_post_now()` e confirmar via polling por `state=PUBLISHED`. Com isso:

  1. não existia caminho de agendamento — aprovar no Telegram sempre
     publicava na hora, ignorando qualquer calendário editorial;
  2. o payload de X ia como `{"__type": "x"}`, sem o campo obrigatório
     `who_can_reply_post` (docs.postiz.com/public-api/providers/x), então o
     Postiz recusava a chamada.

Este arquivo prova o comportamento novo: parsing fail-closed de `publish_at`,
o branch de agendamento (`schedule_post` + `confirm_scheduled`, nunca polling
por PUBLISHED), o payload correto por plataforma, e o card do Telegram
mostrando a data que será usada.

Run:
    pytest tests/goals/test_publish_scheduling.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import heartbeat_outcome  # noqa: E402
import postiz_client  # noqa: E402


def _future(**kw) -> datetime:
    return datetime.now(timezone.utc) + timedelta(**kw)


# ── _parse_publish_at ────────────────────────────────────────────────────


def test_parse_publish_at_absent_means_publish_now():
    for raw in (None, "", "   "):
        dt, err = heartbeat_outcome._parse_publish_at(raw)
        assert dt is None and err is None, f"{raw!r} deveria significar 'publicar agora'"


def test_parse_publish_at_accepts_iso_with_z_and_normalizes_to_utc():
    target = _future(days=3).replace(microsecond=0)
    dt, err = heartbeat_outcome._parse_publish_at(target.isoformat().replace("+00:00", "Z"))
    assert err is None
    assert dt == target
    assert dt.tzinfo is not None


def test_parse_publish_at_assumes_utc_when_naive():
    naive = _future(days=2).replace(microsecond=0, tzinfo=None)
    dt, err = heartbeat_outcome._parse_publish_at(naive.isoformat())
    assert err is None
    assert dt.tzinfo is timezone.utc


def test_parse_publish_at_rejects_past_instead_of_publishing_now():
    """Fail-closed: uma data no passado nunca vira 'publica imediatamente'."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    dt, err = heartbeat_outcome._parse_publish_at(past)
    assert dt is None
    assert err and "passado" in err


def test_parse_publish_at_rejects_garbage_and_wrong_types():
    for raw in ("amanhã de manhã", "2026-13-45T99:00:00Z", 1753400000):
        dt, err = heartbeat_outcome._parse_publish_at(raw)
        assert dt is None and err, f"{raw!r} deveria ser recusado"


def test_parse_publish_at_rejects_beyond_one_year():
    dt, err = heartbeat_outcome._parse_publish_at(_future(days=400).isoformat())
    assert dt is None
    assert err and "365" in err


# ── payload por plataforma ───────────────────────────────────────────────


def test_x_payload_carries_required_who_can_reply_post():
    settings = heartbeat_outcome._publish_settings_for("x", "qualquer texto")
    assert settings["__type"] == "x"
    assert settings["who_can_reply_post"] == "everyone"


def test_x_builder_rejects_invalid_reply_audience():
    with pytest.raises(ValueError):
        postiz_client.build_x_payload(who_can_reply_post="ninguem")


def test_threads_payload_is_type_only():
    assert heartbeat_outcome._publish_settings_for("threads", "texto") == {"__type": "threads"}


def test_youtube_payload_derives_a_schema_valid_title():
    long_first_line = "T" * 250
    settings = heartbeat_outcome._publish_settings_for("youtube", f"{long_first_line}\nresto")
    assert settings["__type"] == "youtube"
    assert 2 <= len(settings["title"]) <= 100


def test_unbuilt_platform_keeps_legacy_generic_shape():
    assert heartbeat_outcome._publish_settings_for("discord", "oi") == {"__type": "discord"}


# ── branch de agendamento em _run_publish_action ─────────────────────────


class _FakeApprovalRow:
    def __init__(self, payload: str):
        self.payload = payload


class _FakeClient:
    """Registra qual caminho do Postiz foi exercitado."""

    def __init__(self, *, confirm_scheduled_result=None):
        self.scheduled_calls = []
        self.now_calls = []
        self.waited_for_publication = False
        self._confirm = confirm_scheduled_result or {
            "scheduled": True, "detail": "Postiz confirmou agendamento."
        }

    def list_integrations(self):
        return [{"id": "int-1", "identifier": "x", "disabled": False}]

    def select_integration(self, target, integrations=None):
        return {"id": "int-1"}

    def is_safe_media_url(self, url):
        return url.startswith("https://")

    def schedule_post(self, *, integration_id, content, media, settings, scheduled_at_utc):
        self.scheduled_calls.append(
            {"content": content, "settings": settings, "at": scheduled_at_utc, "media": media}
        )
        return [{"postId": "post-123"}]

    def create_post_now(self, **kwargs):
        self.now_calls.append(kwargs)
        return [{"postId": "post-now"}]

    def confirm_scheduled(self, post_ids, *, window):
        return self._confirm

    def wait_for_publication(self, *args, **kwargs):
        self.waited_for_publication = True
        return {"published": True, "detail": "publicado"}


@pytest.fixture
def patched_client(monkeypatch):
    holder = {}

    def _install(client):
        holder["client"] = client
        monkeypatch.setattr(postiz_client.PostizClient, "from_env", classmethod(lambda cls: client))
        return client

    return _install


def _approval(outcome_extra: dict) -> _FakeApprovalRow:
    import json

    outcome = {
        "publish_target": "x",
        "publish_content": "Texto exato que vai ao ar.",
        "publish_media": [],
        **outcome_extra,
    }
    return _FakeApprovalRow(json.dumps({"outcome": outcome}))


def test_publish_at_routes_to_schedule_not_publish_now(patched_client):
    client = patched_client(_FakeClient())
    when = _future(days=5).replace(microsecond=0)

    result = heartbeat_outcome._run_publish_action(_approval({"publish_at": when.isoformat()}), conn=None)

    assert result["published"] is True
    assert result["scheduled_at"] == when.isoformat()
    assert len(client.scheduled_calls) == 1, "deveria ter agendado"
    assert client.now_calls == [], "nunca deve publicar imediatamente quando há publish_at"
    assert client.waited_for_publication is False, (
        "um post agendado não está PUBLISHED ainda — nunca fazer polling por PUBLISHED aqui"
    )
    assert client.scheduled_calls[0]["settings"]["who_can_reply_post"] == "everyone"


def test_absent_publish_at_keeps_publishing_immediately(patched_client):
    client = patched_client(_FakeClient())

    result = heartbeat_outcome._run_publish_action(_approval({"publish_at": None}), conn=None)

    assert result["published"] is True
    assert len(client.now_calls) == 1
    assert client.scheduled_calls == []


def test_unconfirmed_schedule_fails_closed(patched_client):
    patched_client(_FakeClient(confirm_scheduled_result={
        "scheduled": False, "detail": "Postiz não retornou o post agendado."
    }))

    result = heartbeat_outcome._run_publish_action(
        _approval({"publish_at": _future(days=1).isoformat()}), conn=None
    )

    assert result["published"] is False, "sem confirmação do Postiz, o ticket não pode resolver"


def test_invalid_publish_at_never_downgrades_to_immediate_publish(patched_client):
    client = patched_client(_FakeClient())

    result = heartbeat_outcome._run_publish_action(
        _approval({"publish_at": "quinta-feira que vem"}), conn=None
    )

    assert result["published"] is False
    assert client.now_calls == [] and client.scheduled_calls == []


# ── card de aprovação no Telegram ────────────────────────────────────────


def test_approval_body_shows_the_scheduled_datetime():
    when = _future(days=4).replace(microsecond=0)
    body = heartbeat_outcome._build_publish_approval_body(
        "x", {"publish_content": "conteúdo", "publish_at": when.isoformat()}
    )
    local = when.astimezone(heartbeat_outcome._PUBLISH_DISPLAY_ZONE)
    assert local.strftime("%d/%m/%Y %H:%M") in body
    assert "Postiz" in body


def test_approval_body_says_immediate_when_not_scheduled():
    body = heartbeat_outcome._build_publish_approval_body("linkedin", {"publish_content": "conteúdo"})
    assert "imediata" in body


def test_approval_body_flags_invalid_schedule():
    body = heartbeat_outcome._build_publish_approval_body(
        "x", {"publish_content": "conteúdo", "publish_at": "sexta que vem"}
    )
    assert "Agendamento inválido" in body


# ── confirm_scheduled é fail-closed ──────────────────────────────────────


def _client_returning(posts):
    client = postiz_client.PostizClient(base_url="https://postiz.example.com", api_key="k")
    client.list_posts = lambda window: posts  # type: ignore[method-assign]
    return client


def test_confirm_scheduled_true_when_post_queued():
    out = _client_returning([{"id": "p1", "state": "QUEUE"}]).confirm_scheduled(["p1"], window=("a", "b"))
    assert out["scheduled"] is True


def test_confirm_scheduled_false_when_post_missing():
    out = _client_returning([]).confirm_scheduled(["p1"], window=("a", "b"))
    assert out["scheduled"] is False


def test_confirm_scheduled_false_on_error_state():
    out = _client_returning([{"id": "p1", "state": "ERROR"}]).confirm_scheduled(["p1"], window=("a", "b"))
    assert out["scheduled"] is False
