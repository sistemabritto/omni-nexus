"""Leitura do Facebook/Meta Ads — Fase 4 do plano de crescimento.

Mensageiro, como `site_analytics.py`: lê a Graph API, normaliza e devolve
medições prontas para `metricas_crescimento.gravar`. Nenhuma interpretação
aqui — o número que a API diz é o número que a gente guarda.

`META_ADS_ACCESS_TOKEN` é um token de usuário de longa duração (sem
`expires_at`, confirmado via `/debug_token` em 29/07/2026) — não um token de
sessão do Graph Explorer, que expira em horas. `META_ADS_ACCOUNT_IDS` é uma
lista separada por vírgula de `act_<id>` (ver `GET /me/adaccounts` pra
descobrir os IDs).
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


class AdsIndisponivel(RuntimeError):
    """A Graph API não respondeu ou recusou a credencial."""


def _token() -> str:
    token = (os.environ.get("META_ADS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise AdsIndisponivel("META_ADS_ACCESS_TOKEN não configurado no .env")
    return token


def _contas() -> list[str]:
    contas = (os.environ.get("META_ADS_ACCOUNT_IDS") or "").strip()
    return [c.strip() for c in contas.split(",") if c.strip()]


def _get(caminho: str, token: str, **params) -> dict:
    try:
        r = requests.get(f"{GRAPH_API}{caminho}", params={**params, "access_token": token}, timeout=30)
    except requests.RequestException as exc:
        raise AdsIndisponivel(f"falha em {caminho}: {exc}") from exc
    corpo = r.json() if r.content else {}
    if r.status_code != 200:
        erro = (corpo.get("error") or {}).get("message", f"HTTP {r.status_code}")
        raise AdsIndisponivel(f"{caminho} recusado: {erro}")
    return corpo


def coletar(*, date_preset: str = "yesterday") -> list[dict]:
    """Lê gasto/impressões/cliques por campanha ativa em cada conta
    configurada. Sem campanha ativa (o caso hoje, 29/07/2026 — nenhuma das
    duas contas tem campanha nenhuma), devolve lista vazia sem erro: conta
    zerada é dado real, não falha de coleta.
    """
    token = _token()
    contas = _contas()
    if not contas:
        raise AdsIndisponivel("META_ADS_ACCOUNT_IDS não configurado no .env")

    from metricas_crescimento import ADS_GASTO, ADS_IMPRESSOES, ADS_CLIQUES

    medicoes: list[dict] = []
    for conta in contas:
        try:
            resp = _get(
                f"/{conta}/insights", token,
                level="campaign", date_preset=date_preset,
                fields="campaign_name,spend,impressions,clicks",
            )
        except AdsIndisponivel as exc:
            log.warning("conta %s indisponível nesta coleta: %s", conta, exc)
            continue

        for linha in resp.get("data") or []:
            origem = (linha.get("campaign_name") or "").strip().lower()
            if not origem:
                continue
            if linha.get("spend") is not None:
                medicoes.append({"metrica": ADS_GASTO, "origem": origem, "valor": float(linha["spend"])})
            if linha.get("impressions") is not None:
                medicoes.append({"metrica": ADS_IMPRESSOES, "origem": origem, "valor": float(linha["impressions"])})
            if linha.get("clicks") is not None:
                medicoes.append({"metrica": ADS_CLIQUES, "origem": origem, "valor": float(linha["clicks"])})

    return medicoes
