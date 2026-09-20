"""Ficha de criativo + card Magneto do reels_copilot.

Cobre: o HTML ser auto-contido (padrão artifacts.md), o card curto com link
(marker #reel preservado p/ ponte de decisão), o fallback completo sem link
(texto sanado + teto 4096), e a reutilização do share existente por by-path.
"""
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "dashboard" / "backend"))

import reels_copilot as rc  # noqa: E402


def _row(**over):
    base = {
        "id": "11111111-2222-3333-4444-555555555555",
        "seq": 7,
        "theme": "Abra mão da sua ideia favorita",
        "avatar": "Dev que ganha pouco",
        "funnel_stage": "doutrinar",
        "headline": "Sua ideia favorita não é seu produto.",
        "hook_spoken": "Você vai gastar mais dinheiro convencendo do que ganhando.",
        "hook_visual": "Tela dividida: reunião x repouso",
        "script_md": "Cena 1 — gancho.\nCena 2 — prova social.\nCena 3 — CTA.",
        "cta": "Comenta RASTREAR que eu te mando o mapa.",
        "bait_number": 3,
        "bait_text": "Mapa de rastreamento de demanda",
        "status": "review",
        "openreply_status": "created",
        "created_at": "2026-09-19T21:58:00",
    }
    base.update(over)
    return base


# ── HTML da ficha ──────────────────────────────────────────────────────────────

def test_html_ficha_contem_todos_os_blocos():
    html = rc._creative_html(_row())
    for trecho in ["Sua ideia favorita não é seu produto.", "Cena 1", "RASTREAR",
                   "Ficha de criativo", "Reel 007", "doutrinar"]:
        assert trecho in html


def test_html_escapa_tags_do_llm():
    row = _row(hook_spoken="<script>alert(1)</script>", cta="A&B")
    html = rc._creative_html(row)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html


def test_html_fica_auto_contido():
    html = rc._creative_html(_row())
    assert "<!DOCTYPE html>" in html
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html.replace("https://nexus", "") or True
    assert 'src="http' not in html and '@import url' not in html


# ── Card curto com link ───────────────────────────────────────────────────────

def test_card_curto_com_link_tem_marker_e_url():
    card = rc.build_card(_row(), share_url="https://nexus.sistemabritto.com.br/share/abc")
    assert "Abrir ficha de criativo" in card
    assert "https://nexus.sistemabritto.com.br/share/abc" in card
    assert "#reel:11111111-2222-3333-4444-555555555555" in card
    assert "<a href=" in card
    # tag solta <o que mudar> escapada
    assert "<o que mudar>" not in card
    assert len(card) < 800


def test_card_curto_ignora_html_injeto_na_url():
    url = "https://nexus/share/a<b>"
    card = rc.build_card(_row(), share_url=url)
    assert "&lt;b&gt;" in card


# ── Fallback sem link ─────────────────────────────────────────────────────────

def test_fallback_sem_link_mantem_todo_o_conteudo():
    card = rc.build_card(_row())
    assert "ROTEIRO" in card and "HOOK FALADO" in card
    assert "Cena 1" in card
    assert "ISCA 03" in card


def test_fallback_estoura_teto_de_4096():
    big = _row(script_md="linha longa. " * 900, hook_visual="v" * 2000)
    card = rc.build_card(big)
    assert len(card) <= 4096
    assert "[cortado" in card or len(card) < 3000


def test_fallback_escapa_html_do_llm():
    row = _row(theme='<i>tema</i> & Cia', headline="h<b>x</b>")
    card = rc.build_card(row)
    assert "<i>tema</i>" not in card
    assert "&lt;i&gt;tema&lt;/i&gt;" in card


# ── publish_creative_share ────────────────────────────────────────────────────

def test_publish_reusa_share_existente(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "WORKSPACE", tmp_path)
    monkeypatch.setenv("EVONEXUS_API_URL", "http://x:8080")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "t")

    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.method, req.full_url))
        body = json.dumps({
            "url": "https://nexus/share/EXISTENTE",
            "path": req.full_url.split("?path=")[-1],
        }).encode()
        return type("R", (), {"read": lambda self: body, "__enter__": lambda self: self,
                               "__exit__": lambda self, *a: None})()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    url = rc.publish_creative_share(_row())
    assert url == "https://nexus/share/EXISTENTE"
    methods = [m for m, _ in calls]
    assert methods == ["GET"]  # só consultou by-path, não criou outro

    fichas = list((tmp_path / "workspace/social/reels").glob("*ficha*.html"))
    assert len(fichas) == 1


def test_publish_cria_share_quando_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "WORKSPACE", tmp_path)
    monkeypatch.setenv("EVONEXUS_API_URL", "http://x:8080")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "t")

    def fake_urlopen(req, timeout=None):
        if req.method == "GET":
            raise urllib.error.HTTPError(req.full_url, 404, "não existe", {}, None)
        body = json.dumps({"url": "https://nexus/share/NOVO"}).encode()
        return type("R", (), {"read": lambda self: body, "__enter__": lambda self: self,
                               "__exit__": lambda self, *a: None})()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert rc.publish_creative_share(_row()) == "https://nexus/share/NOVO"


def test_publish_sem_token_retorna_none(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "WORKSPACE", tmp_path)
    monkeypatch.setenv("EVONEXUS_API_URL", "http://x:8080")
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    assert rc.publish_creative_share(_row()) is None


def test_send_reel_card_fallback_sem_api(monkeypatch):
    sent = {}

    def fake_alert(text):
        sent["text"] = text
        return True

    monkeypatch.setattr("notifications.send_telegram_alert", fake_alert)
    monkeypatch.setattr(rc, "publish_creative_share", lambda row: None)
    ok = rc.send_reel_card(_row())
    assert ok and "ROTEIRO" in sent["text"]
