"""Leitura do analytics de sistemabritto.com.br.

O site já media tudo e ninguém no Nexus sabia. Em `pages/api/admin/` existem
`analytics.ts` (pageviews com utm_source, cta_clicks, funil do quiz) e
`leads.ts` (pipeline com estágios) — tudo sobre Supabase, servido com token.

Este módulo é só o mensageiro: faz login, lê, normaliza e devolve medições
prontas para `metricas_crescimento.gravar`. Nada de interpretação aqui — o
número que o site diz é o número que a gente guarda.

A senha vive em `SITE_ADMIN_PASSWORD` no .env da VPS. Não vai para o
repositório, e o .env não viaja no deploy: é um arquivo da máquina.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

BASE = (os.environ.get("SITE_ADMIN_URL") or "https://www.sistemabritto.com.br").rstrip("/")

# Rotas de funil. Só estas contam como "visita de funil" — a home recebe a
# maior parte do tráfego e misturá-la mascararia se o conteúdo está de fato
# empurrando gente para a oferta.
FUNIS = ("/whatsapp", "/socialjobs", "/sistema")


class SiteIndisponivel(RuntimeError):
    """O site não respondeu ou recusou a credencial."""


def _token() -> str:
    senha = (os.environ.get("SITE_ADMIN_PASSWORD") or "").strip()
    if not senha:
        raise SiteIndisponivel("SITE_ADMIN_PASSWORD não configurada no .env")
    try:
        r = requests.post(f"{BASE}/api/admin/auth", json={"password": senha}, timeout=30)
    except requests.RequestException as exc:
        raise SiteIndisponivel(f"site inacessível: {exc}") from exc
    if r.status_code != 200:
        # A senha nunca entra na mensagem — ela vaza para log e para ticket.
        raise SiteIndisponivel(f"login recusado pelo site ({r.status_code})")
    token = (r.json() or {}).get("token")
    if not token:
        raise SiteIndisponivel("login respondeu 200 sem token")
    return token


def _get(caminho: str, token: str, **params) -> dict:
    try:
        r = requests.get(f"{BASE}{caminho}", params=params or None,
                         headers={"Authorization": f"Bearer {token}"}, timeout=45)
    except requests.RequestException as exc:
        raise SiteIndisponivel(f"falha em {caminho}: {exc}") from exc
    if r.status_code != 200:
        raise SiteIndisponivel(f"{caminho} respondeu {r.status_code}")
    try:
        return r.json() or {}
    except ValueError as exc:
        raise SiteIndisponivel(f"{caminho} devolveu corpo não-JSON") from exc


def coletar(*, janela: str = "7d") -> list[dict]:
    """Lê o site e devolve medições prontas para gravar.

    Janela de 7 dias por padrão, não 30: a rotina roda todo dia, e uma janela
    curta faz cada ponto da série refletir o período recente em vez de arrastar
    um mês inteiro de história a cada medição.
    """
    from metricas_crescimento import (CLIQUES_CTA, LEADS, LEADS_FECHADOS,
                                      VISITANTES, VISITAS, VISITAS_FUNIL)

    token = _token()
    a = _get("/api/admin/analytics", token, range=janela)

    medicoes: list[dict] = [
        {"metrica": VISITAS, "valor": a.get("totalPageviews") or 0},
        {"metrica": VISITANTES, "valor": a.get("uniqueVisitors") or 0},
        {"metrica": CLIQUES_CTA, "valor": a.get("totalCtaClicks") or 0},
    ]

    # Visitas por origem: é o que responde "o conteúdo está trazendo gente?".
    for item in (a.get("trafficBySource") or []):
        origem = (item.get("source") or "").strip().lower()
        if origem:
            medicoes.append({"metrica": VISITAS, "origem": origem,
                             "valor": item.get("views") or 0})

    # Visitas que chegaram às páginas de oferta, somadas e por funil.
    paginas = {p.get("path"): p.get("views") or 0 for p in (a.get("topPages") or [])}
    total_funil = 0
    for rota in FUNIS:
        visitas = paginas.get(rota, 0)
        total_funil += visitas
        medicoes.append({"metrica": VISITAS_FUNIL, "origem": rota.lstrip("/"),
                         "valor": visitas})
    medicoes.append({"metrica": VISITAS_FUNIL, "valor": total_funil})

    # Leads: o número que de fato importa. O endpoint devolve o pipeline
    # inteiro com contagem por estágio.
    try:
        leads = _get("/api/admin/leads", token)
        medicoes.append({"metrica": LEADS, "valor": leads.get("total") or 0})
        for est in (leads.get("stages") or []):
            nome = (est.get("name") or "").strip().lower()
            if nome:
                medicoes.append({"metrica": LEADS, "origem": nome,
                                 "valor": est.get("count") or 0})
            if nome == "fechado":
                medicoes.append({"metrica": LEADS_FECHADOS, "valor": est.get("count") or 0})
    except SiteIndisponivel as exc:
        # Analytics sem leads ainda vale a coleta — perder tudo porque um dos
        # dois endpoints falhou seria trocar dado parcial por dado nenhum.
        log.warning("leads indisponíveis nesta coleta: %s", exc)

    return medicoes
