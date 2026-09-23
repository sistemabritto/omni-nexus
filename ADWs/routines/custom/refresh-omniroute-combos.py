#!/usr/bin/env python3
"""ADW: OmniRoute Combo Refresh — mantém os combos Britto-* vivos via Atlas

Problema que resolve: providers aposentam/renomeiam modelos (ex.: deepseek
deepseek-v4-flash-0731 -> 410 EOL; agy gemini-3.6-flash-medium -> 3.7; codex
ganhou Sol/Luna em 2026-09). As pernas mortas ficam nos combos e pesam no
scoring (request cai nelas e o fallback corrige, mas queima latência + confunde
o LKGP). Este script:

  1. Puxa o catálogo AO VIVO de /v1/models (fonte de verdade: só entra no
     catálogo o que o gateway realmente consegue servir agora).
  2. Compara cada combo Britto-* contra o catálogo e marca pernas MORTAS
     (modelo não existe no catálogo e nenhum alias por nome-sufixo casa).
  3. --report (default): só imprime o diagnóstico.
  4. --apply: remove as pernas mortas e renormaliza pesos relativos
     (OmniRoute normaliza pelos pesos restantes, então remover basta).
  5. --add (junto com --apply): injeta modelos novos de um map ADD_BELOW.

Autenticação:
  - leitura do catálogo: OPENAI_API_KEY (chave de inferência, escopo self).
  - escrita de combos: OMNIROUTE_MANAGE_KEY (OMNIROUTE_API_KEY no serviço — o
    código do OmniRoute dá escopo 'manage' incondicional pra essa env key).

Uso:
  python3 omniroute_combo_refresh.py            # report
  python3 omniroute_combo_refresh.py --apply     # remove mortas
  python3 omniroute_combo_refresh.py --apply --add  # remove + injeta novos
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("OMNI_BASE_URL", "https://omni.sistemabritto.com.br")
MANAGE_KEY = (os.environ.get("OMNIROUTE_MANAGE_KEY")
              or os.environ.get("OMNIROUTE_API_KEY", "")).strip()
# A env key OMNIROUTE_API_KEY tem escopo 'manage' incondicional no OmniRoute —
# serve p/ ler /v1/models E escrever combos. OPENAI_API_KEY é fallback de leitura
# quando a manage key não está no ambiente. No container do scheduler a OMNI_KEY
# (sk-...) que já existe no env do serviço é a mesma chave de inferência usada
# pelos ADWs, então entra como último fallback de leitura.
INFER_KEY = os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("OMNI_KEY", "").strip() or MANAGE_KEY
READ_KEY = MANAGE_KEY or INFER_KEY


def _load_dotenv_if_needed():
    """Auto-suficiência: se as chaves não vierem no ambiente (scheduler do Swarm
    só tem OMNI_KEY/OMNIROUTE_URL), tenta fontes persistentes em ordem:
      1. config volume  -> /workspace/config/omni_manage_key  (token puro)
      2. .env do workspace -> OPENAI_API_KEY / OMNIROUTE_MANAGE_KEY
    A manage key fica em arquivo no config volume de propósito pra sobreviver
    redeploy (o .env raiz do container vem da imagem e some no redeploy)."""
    global MANAGE_KEY, INFER_KEY, READ_KEY
    ws = Path("/workspace")
    # 1) chave de gestão persistente no config volume
    if not MANAGE_KEY:
        kf = ws / "config" / "omni_manage_key"
        if not kf.exists():
            kf = Path(__file__).resolve().parents[1] / "config" / "omni_manage_key"
        if kf.exists():
            MANAGE_KEY = kf.read_text().strip()
    # 2) .env do workspace
    if not (MANAGE_KEY or INFER_KEY):
        cand = ws / ".env"
        if not cand.exists():
            cand = Path(__file__).resolve().parents[1] / ".env"
        if cand.exists():
            for line in cand.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "OPENAI_API_KEY" and not INFER_KEY:
                    INFER_KEY = v
                if k == "OMNIROUTE_MANAGE_KEY" and not MANAGE_KEY:
                    MANAGE_KEY = v
    READ_KEY = MANAGE_KEY or INFER_KEY


_load_dotenv_if_needed()

COMBOS = ["britto-fast", "britto-core", "britto-coding", "britto-heavy",
          "britto-free", "britto-voice", "britto-spicy", "britto-drael"]

# Modelos a INJETAR quando --add passa. Chave = combo, valor = lista de
# {model, providerId, weight}. Só adiciona se ainda não existir no combo.
ADD_BELOW = {
    # Codex Sol/Luna voltaram em 2026-09 — entram como opções de reasoning/coding premium.
    "britto-coding": [
        {"model": "codex/gpt-5.6-sol-medium", "providerId": "codex", "weight": 8},
        {"model": "codex/gpt-5.6-luna-medium", "providerId": "codex", "weight": 4},
    ],
    "britto-heavy": [
        {"model": "codex/gpt-5.6-sol-xhigh", "providerId": "codex", "weight": 8},
        {"model": "codex/gpt-5.6-luna-max", "providerId": "codex", "weight": 4},
    ],
    # agy aposentou gemini-3.6-flash-medium -> linha 3.7 (catálogo 2026-09-23).
    "britto-free": [
        {"model": "agy/gemini-3.7-flash-medium", "providerId": "agy", "weight": 14},
    ],
}

# Modelos MORTOS na hora mesmo estando no catálogo (o gateway lista, o
# upstream responde 4xx). Mantenha aqui o que for confirmado em produção;
# o report mostra as suspeitas pra você adicionar depois. Ex.: deepseek-v4-flash-0731
# sumiu no NVIDIA (410 model_shutdown, EOL 2026-09-14).
OVERRIDES_DEAD = {
    "nvidia/deepseek-ai/deepseek-v4-flash-0731",
}


UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _get(url, key=None, timeout=60):
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": UA})
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _put(url, payload, key, timeout=60):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PUT",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": UA,
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_catalog():
    data = _get(f"{BASE}/v1/models", key=READ_KEY)
    ids = {m["id"] for m in data.get("data", [])}
    return ids


def alias_match(model_id, catalog):
    """Casa por sufixo de nome (o catálogo lista o mesmo modelo com vários
    provider prefixes: codex/x vs cx/x). Se algum membro do catálogo termina
    igual ao nosso, consideramos vivo."""
    tail = model_id.split("/")[-1]
    return any(c.split("/")[-1] == tail for c in catalog)


def get_combo(cid):
    combos = _get(f"{BASE}/api/combos", key=READ_KEY).get("combos", [])
    for c in combos:
        if c.get("id") == cid or (c.get("name") or "").lower() == cid.lower():
            return c
    return None


def diagnose(combo, catalog):
    alive, dead = [], []
    for m in combo.get("models", []):
        mid = m.get("model", "")
        in_catalog = mid in catalog or alias_match(mid, catalog)
        if not in_catalog or mid in OVERRIDES_DEAD:
            dead.append(m)
        else:
            alive.append(m)
    return alive, dead


def main():
    args = set(sys.argv[1:])
    do_apply = "--apply" in args
    do_add = "--add" in args
    if not (INFER_KEY or MANAGE_KEY):
        sys.exit("FALTA OPENAI_API_KEY e OMNIROUTE_MANAGE_KEY (leitura do catálogo)")
    if do_apply and not MANAGE_KEY:
        sys.exit("FALTA OMNIROUTE_MANAGE_KEY (escrita de combos)")

    print("Puxando catálogo ao vivo...")
    catalog = fetch_catalog()
    print(f"  {len(catalog)} modelos no catálogo\n")

    # Guarda contra catálogo parcial: se o fetch retornar bem menos modelos do
    # que o mínimo, podemos dar falso positivo e remover uma perna viva. Em
    # modo --apply, aborta o WRITE nesse caso (o relatório continua).
    min_catalog = int(os.environ.get("OMNI_MIN_CATALOG", "700"))
    catalog_partial = len(catalog) < min_catalog
    if catalog_partial and do_apply:
        print(f"  [GUARDA] catálogo {len(catalog)} < mínimo {min_catalog} "
              f"(parcial?) — só report, sem escrita hoje.\n")

    changed_any = False
    for cid in COMBOS:
        combo = get_combo(cid)
        if not combo:
            print(f"  [?!] {cid}: combo não encontrado, pulando")
            continue
        alive, dead = diagnose(combo, catalog)
        if dead:
            names = ", ".join(f"{m['model']}(w={m.get('weight',0)})" for m in dead)
            print(f"  [MORTAS] {combo['name']}: {len(dead)} -> {names}")
        else:
            print(f"  [OK]     {combo['name']} ({len(alive)} pernas vivas)")

        if do_apply and not catalog_partial and dead:
            kept = [m for m in combo["models"] if m not in dead]
            # --add: injeta modelos novos que ainda não existem
            existing = {m["model"] for m in kept}
            added = []
            for cand in ADD_BELOW.get(cid, []):
                if cand["model"] not in existing:
                    kept.append(dict(cand))
                    added.append(cand["model"])
            payload = {"id": combo["id"], "name": combo["name"],
                       "strategy": combo.get("strategy", "weighted"),
                       "isActive": combo.get("isActive", True),
                       "models": kept}
            _put(f"{BASE}/api/combos/{combo['id']}", payload, MANAGE_KEY)
            removed = ", ".join(m["model"] for m in dead)
            msg = f"removi {len(dead)} morta(s): {removed}"
            if added:
                msg += f"; adicionei {len(added)}: {', '.join(added)}"
            print(f"      ↳ APLICADO em {combo['name']}: {msg}")
            changed_any = True
            # renormalização: o OmniRoute usa peso relativo; deixamos os
            # valores como estão (proporção preservada).

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    print(f"\n{'='*50}\n{ts} {'APPLY' if do_apply else 'REPORT'} concluído."
          f" {'Combos atualizados.' if changed_any else 'Sem mudanças.'}")
    if not do_apply and changed_any is False:
        pass


if __name__ == "__main__":
    main()
