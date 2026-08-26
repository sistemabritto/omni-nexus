#!/usr/bin/env python3
"""Self-healing: limpa o cache LKGP do OmniRoute quando um modelo se aposenta.

O OmniRoute guarda, por combo (`auto/coding`, `auto/reasoning`, etc), qual foi
o último provider/model que respondeu com sucesso — o "Last Known Good
Provider" (LKGP). Isso acelera a escolha em condições normais. O problema:
quando esse modelo cacheado se aposenta (410 Gone, "reached its end of life"),
o OmniRoute não invalida a entrada sozinho — cada request novo tenta primeiro
o cache morto, toma 410, e só depois cicla pelo resto da pool (às vezes 100+
candidatos) até achar algo vivo.

Confirmado ao vivo em 25/08/2026: `z-ai/glm-5.2` (aposentado em 21/08) ficou
preso no LKGP de `auto/coding`. Toda chamada de Magneto/Hermes que caía nesse
combo pagava a taxa de ciclar a pool inteira antes de responder — em alguns
casos isso somava aos 45-180s de timeout por tentativa e o pedido inteiro
falhava sem nunca chegar num modelo vivo. `DELETE /api/settings/lkgp-cache`
resolveu na hora (confirmado: `auto/coding` passou a responder em 2-7s,
direto em Claude, sem tentar o modelo morto). Esta rotina existe para nunca
mais depender de alguém notar isso na mão.

Detecção, não achismo: só limpa quando o `errorCode` da connection é do tipo
PERMANENTE (410 Gone, 404, ou a mensagem cita fim de vida/descontinuação).
Erro transitório (429 rate limit, 5xx passageiro) nunca dispara a limpeza —
isso destruiria a própria utilidade do cache durante um pico normal de uso,
que é exatamente o cenário que o LKGP existe para suavizar.

Idempotente por incidente, não por tick: um arquivo de estado guarda a
assinatura do último erro tratado. Rodar a cada 15 minutos não manda alerta
novo a cada tick enquanto o mesmo erro antigo ainda aparece nos logs — só
quando a assinatura muda (modelo diferente aposentou) ou quando o mesmo erro
persiste por mais de `REINCIDENCIA_HORAS` depois de já ter sido "resolvido"
(sinal de que a limpeza não bastou e precisa de olho humano).

Secrets (env da stack no Portainer, nunca aqui):
  OMNIROUTE_URL             → https://omni.workflowapi.com.br (default)
  OMNIROUTE_ADMIN_PASSWORD  → senha de login do dashboard do OmniRoute
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

STATE_PATH = REPO / "ADWs" / "logs" / "omniroute-lkgp-healer-state.json"
# Mesmo erro reaparecendo depois desta janela desde a última limpeza = a
# limpeza não resolveu de verdade (outra coisa mantém o modelo morto no
# topo da pool). Vale alertar de novo, escalado, em vez de ficar calado.
REINCIDENCIA_HORAS = 6

# Só isso conta como "aposentado pra sempre" — qualquer coisa fora daqui é
# tratada como transitório e NUNCA dispara a limpeza. Rate limit (429) e erro
# de servidor (5xx) são exatamente o que o LKGP existe para amortecer.
CODIGOS_PERMANENTES = {"410", "404"}
FRASES_PERMANENTES = (
    "end of life", "no longer available", "deprecated", "descontinuad",
    "decommissioned", "has been removed", "sunset",
)


def carregar_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for linha in env.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _http(method: str, url: str, *, token: str | None = None,
          body: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Cookie", f"auth_token={token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def login(base_url: str, senha: str) -> str:
    """Cookie de sessão fresco a cada execução — mais simples e mais robusto
    que tentar guardar/renovar um token entre execuções de uma rotina que só
    roda a cada 15 minutos."""
    resp = _http("POST", f"{base_url}/api/auth/login", body={"password": senha})
    if not resp.get("success"):
        raise RuntimeError(f"login no OmniRoute falhou: {resp}")
    # A API devolve o cookie via Set-Cookie, não no corpo — refazendo a
    # chamada com urllib puro (sem lib de sessão) para não adicionar
    # dependência só por isto. Extrai do header manualmente.
    req = urllib.request.Request(
        f"{base_url}/api/auth/login", method="POST",
        data=json.dumps({"password": senha}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        for header, valor in r.getheaders():
            if header.lower() == "set-cookie" and valor.startswith("auth_token="):
                return valor.split(";", 1)[0].split("=", 1)[1]
    raise RuntimeError("login OK mas nenhum cookie auth_token na resposta")


def erro_e_permanente(codigo: str | None, mensagem: str | None) -> bool:
    if codigo and str(codigo).split(".")[0] in CODIGOS_PERMANENTES:
        return True
    texto = (mensagem or "").lower()
    return any(frase in texto for frase in FRASES_PERMANENTES)


def ler_estado() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def gravar_estado(estado: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def main() -> int:
    carregar_env()
    base_url = (os.environ.get("OMNIROUTE_URL") or "https://omni.workflowapi.com.br").rstrip("/")
    senha = (os.environ.get("OMNIROUTE_ADMIN_PASSWORD") or "").strip()
    if not senha:
        print("OMNIROUTE_ADMIN_PASSWORD não configurada — sem ela não dá para "
              "logar no OmniRoute e checar as connections. Pulando.")
        return 0  # não é falha da rotina, é falta de configuração — não alerta

    try:
        token = login(base_url, senha)
        connections = _http("GET", f"{base_url}/api/providers", token=token).get("connections", [])
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"não consegui checar o OmniRoute agora ({exc}) — tenta de novo no próximo tick")
        return 0  # transitório por definição — nunca falha a rotina por isso

    culpados = [
        c for c in connections
        if c.get("testStatus") == "unavailable"
        and erro_e_permanente(c.get("errorCode"), c.get("lastError"))
    ]
    if not culpados:
        return 0  # caso normal — sem log, mesmo motivo do varredor de redes

    estado = ler_estado()
    agora = time.time()
    limpou = False

    for c in culpados:
        assinatura = f"{c.get('provider')}:{c.get('errorCode')}:{(c.get('lastError') or '')[:120]}"
        anterior = estado.get(assinatura)
        # Só o RELÓGIO decide se já foi tratado — nada de flag "já avisei"
        # separada. `testStatus` costuma continuar `unavailable` por um
        # tempo depois do clear, até a próxima chamada real reciclar a pool;
        # sem essa janela, a rotina limparia (e avisaria) de novo no PRÓPRIO
        # tick seguinte ao primeiro clear, antes de dar tempo do fix pegar.
        if anterior and (agora - anterior.get("limpo_em", 0)) < REINCIDENCIA_HORAS * 3600:
            continue

        # Existia um registro, mas passou da janela: o mesmo erro voltou
        # depois de já ter sido "resolvido" — não é mais cache frio, é
        # reincidência de verdade. Ainda assim vale tentar limpar de novo
        # (self-healing não desiste), só que agora também escala pra humano.
        reincidencia = anterior is not None

        try:
            resultado = _http("DELETE", f"{base_url}/api/settings/lkgp-cache", token=token)
        except (urllib.error.URLError, RuntimeError) as exc:
            print(f"clear do LKGP falhou para {c.get('provider')}: {exc}")
            continue

        if resultado.get("cleared"):
            limpou = True
            estado[assinatura] = {"limpo_em": agora}
            if reincidencia:
                notify_reincidencia(c, assinatura)
            else:
                notify_limpeza(c)
            print(f"LKGP limpo — {c.get('provider')} estava preso em erro permanente: "
                  f"{c.get('lastError')}")

    if limpou:
        gravar_estado(estado)
    return 0


def notify_limpeza(connection: dict) -> None:
    try:
        from notifications import notify_info
        notify_info(
            "OmniRoute: cache LKGP limpo automaticamente",
            f"Provider '{connection.get('provider')}' estava preso num erro permanente "
            f"({connection.get('errorCode')}) — provavelmente um modelo aposentado. "
            f"Cache de \"last known good provider\" limpo sozinho. "
            f"Detalhe: {(connection.get('lastError') or '')[:200]}",
        )
    except Exception as exc:  # noqa: BLE001 — alerta nunca derruba a rotina
        print(f"não consegui alertar sobre a limpeza: {exc}")


def notify_reincidencia(connection: dict, assinatura: str) -> None:
    try:
        from notifications import notify_info
        notify_info(
            f"OmniRoute: mesmo erro voltou depois de {REINCIDENCIA_HORAS}h",
            f"Já limpei o cache LKGP para '{connection.get('provider')}' uma vez, e o "
            f"mesmo erro reapareceu. Isso não é mais coisa de cache — vale olhar na mão. "
            f"Assinatura: {assinatura[:200]}",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"não consegui alertar sobre a reincidência: {exc}")


if __name__ == "__main__":
    sys.exit(main())
