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
import re
from datetime import datetime, timedelta, timezone

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


def _janela_em_dias(janela: str) -> int:
    m = re.match(r"^(\d+)d$", (janela or "").strip())
    return int(m.group(1)) if m else 7


def _dentro_da_janela(item: dict, campo: str, corte: datetime) -> bool:
    """`created_at`/`entered_at` do endpoint já vêm em ISO 8601 (ver
    `pages/api/admin/leads.ts::handler`, que converte o unix timestamp do
    EvoCRM). Item sem o campo (nunca deveria acontecer, mas a API é externa)
    não conta como novo — melhor subcontar que estourar a coleta inteira."""
    bruto = item.get(campo)
    if not bruto:
        return False
    try:
        quando = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return False
    return quando >= corte


def coletar(*, janela: str = "7d") -> list[dict]:
    """Lê o site e devolve medições prontas para gravar.

    Janela de 7 dias por padrão, não 30: a rotina roda todo dia, e uma janela
    curta faz cada ponto da série refletir o período recente em vez de arrastar
    um mês inteiro de história a cada medição.
    """
    from metricas_crescimento import (CLIQUES_CTA, CLIQUES_POR_ARTIGO, LEADS,
                                      LEADS_FECHADOS, LEADS_FECHADOS_NOVOS,
                                      LEADS_NOVOS, VISITANTES, VISITAS,
                                      VISITAS_FUNIL)

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

    # Cliques por origem e por artigo. Visita diz que a pessoa chegou; clique
    # diz que o conteúdo convenceu. Sem esta separação, um artigo que traz mil
    # visitas e nenhum clique parece igual a um que traz cem e converte dez.
    #
    # O site atribui o clique pela sessão: o session_id do clique é o mesmo do
    # pageview de entrada, que carregou a UTM. Ausente até 27/07/2026, quando
    # nenhum botão do site chamava trackCta e a tabela tinha 1 linha.
    atribuicao = a.get("attribution") or {}
    for item in (atribuicao.get("bySource") or []):
        origem = (item.get("source") or "").strip().lower()
        if origem:
            medicoes.append({"metrica": CLIQUES_CTA, "origem": origem,
                             "valor": item.get("clicks") or 0})
    for item in (atribuicao.get("byCampaign") or []):
        artigo = (item.get("campaign") or "").strip().lower()
        if artigo:
            medicoes.append({"metrica": CLIQUES_POR_ARTIGO, "origem": artigo,
                             "valor": item.get("clicks") or 0})

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
    # inteiro com contagem por estágio (estoque) E a lista achatada de itens
    # com created_at/entered_at (o que dá pra medir fluxo).
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

        # Fluxo da janela, não estoque — achado ao vivo em 11/09/2026 (ver
        # comentário em metricas_crescimento.py junto de LEADS_NOVOS): o
        # pipeline "Leads do Site" carrega 52 itens estáticos de uma lista de
        # reconexão histórica, e LEADS/LEADS_FECHADOS acima travam nesse
        # estoque toda semana. `leads_novos` conta quem foi CRIADO na janela;
        # `leads_fechados_novos` conta quem ENTROU no estágio Fechado na
        # janela (aproximação: item currently em Fechado com entered_at
        # recente — não dá pra saber por quanto tempo passou por estágio
        # intermediário sem histórico de transição, que a API não expõe).
        corte = datetime.now(timezone.utc) - timedelta(days=_janela_em_dias(janela))
        itens = leads.get("leads") or []
        novos = sum(1 for it in itens if _dentro_da_janela(it, "created_at", corte))
        fechados_novos = sum(
            1 for it in itens
            if (it.get("stage") or "").strip().lower() == "fechado"
            and _dentro_da_janela(it, "entered_at", corte)
        )
        medicoes.append({"metrica": LEADS_NOVOS, "valor": novos})
        medicoes.append({"metrica": LEADS_FECHADOS_NOVOS, "valor": fechados_novos})
    except SiteIndisponivel as exc:
        # Analytics sem leads ainda vale a coleta — perder tudo porque um dos
        # dois endpoints falhou seria trocar dado parcial por dado nenhum.
        log.warning("leads indisponíveis nesta coleta: %s", exc)

    return medicoes
