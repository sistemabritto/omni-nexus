"""hb_reconcile — aplica config/heartbeats.yaml ao banco, mata o drift YAML↔DB.

Problema (ver workspace/strategy/[C]cascade-evergreen-plan.md, Bloco A1):
`heartbeat_dispatcher._sync_heartbeats_to_db` preserva o `enabled` definido pela
UI e ignora o valor do YAML para linhas já existentes. Consequência:
`config/heartbeats.yaml` deixa de ser fonte de verdade e o estado real vive num
toggle do dashboard que ninguém enxerga ao ler o arquivo — foi assim que
`goal-planner` ficou com yaml `true` / db `false` e nenhum Goal novo virou ticket
sozinho por dias.

Este módulo inverte a relação: **o YAML manda.** `reconcile()` lê o YAML (core +
plugins, via heartbeat_schema.load_heartbeats_yaml) e, para cada id que existe nos
dois lados, aplica os campos mutáveis do YAML ao banco — incluindo `enabled`.
Onde o sync do dispatcher era "DB vira espelho, menos enabled", aqui é
"DB vira espelho, inclusive enabled".

Guardrails:
- Não deleta: heartbeat que está só no DB (criado pela UI) não é apagado; delete
  continua sendo decisão humana (DELETE /api/heartbeats/<id>).
- `goal_id`: o YAML manda SÓ quando explicita um valor. YAML `goal_id: null`
  preserva o `goal_id` que foi setado pela UI (intent humano explícito vale mais
  que o null genérico do YAML) — igual à regra do reindex atual.
- Operar em sqlite diretamente (convenção do motor: dispatcher, runner e
  nexus_orchestrator abrem sqlite3, não dependem de app-context Flask). Assim o
  reconcile roda tanto no endpoint (dentro do app) quanto num subprocess/CLI.

WAL: o SQLite permite 1 writer + N readers; o reconcile é uma escrita pontual de
milissegundos, segura ao lado do processo dashboard lendo.
"""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"

# Campos mutáveis que o YAML manda sobre o banco (espelha _mirror_to_db, menos o
# cuidado especial de enabled/goal_id tratado abaixo).
_FIELDS = (
    "agent", "interval_seconds", "max_turns", "timeout_seconds",
    "lock_timeout_seconds", "decision_prompt", "handler",
)


def _get_db():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _load_yaml():
    import sys
    backend_dir = Path(__file__).resolve().parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from heartbeat_schema import load_heartbeats_yaml
    return load_heartbeats_yaml(include_plugins=True)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _yaml_value(hb, field: str):
    """Extrai o valor 'serializável' de um campo do HeartbeatConfig."""
    val = getattr(hb, field)
    if field == "wake_triggers":
        return json.dumps(list(val))
    if field == "required_secrets":
        return json.dumps(list(val))
    return val


def diff(db_path: Path | None = None, dry_run: bool = True) -> list[dict]:
    """Lista as mudanças que reconcile() faria (YAML → DB).

    Retorna [{"id", "field", "from", "to"}]. Vazio = banco já alinhado ao YAML.
    `dry_run` não altera nada — o diff é sempre read-only.
    """
    conn = _db(db_path)
    try:
        cfg = _load_yaml()
        out: list[dict] = []
        for hb in cfg.heartbeats:
            row = conn.execute("SELECT * FROM heartbeats WHERE id=?", (hb.id,)).fetchone()
            if not row:
                # Novo no YAML, ainda não existe no DB — reconcile() criará.
                out.append({"id": hb.id, "field": "*create*", "from": None, "to": hb.agent})
                continue
            # campos fixos (string/num)
            for field in _FIELDS:
                yval = _yaml_value(hb, field)
                if field in ("wake_triggers", "required_secrets"):
                    dval = row[field] or "[]"
                else:
                    dval = row[field]
                if dval != yval:
                    out.append({"id": hb.id, "field": field, "from": dval, "to": yval})
            # enabled — o coração do reconciliador: YAML manda
            y_enabled = 1 if hb.enabled else 0
            d_enabled = 1 if row["enabled"] else 0
            if d_enabled != y_enabled:
                out.append({"id": hb.id, "field": "enabled", "from": bool(d_enabled), "to": bool(y_enabled)})
            # goal_id — só aplica se YAML explicita (null preserva o da UI)
            if hb.goal_id is not None and (row["goal_id"] != hb.goal_id):
                out.append({"id": hb.id, "field": "goal_id", "from": row["goal_id"], "to": hb.goal_id})
        return out
    finally:
        conn.close()


def _db(path: Path | None):
    import sqlite3
    conn = sqlite3.connect(str(path or DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def reconcile(db_path: Path | None = None, dry_run: bool = False) -> dict:
    """Aplica o YAML ao banco (upsert idempotente). Retorna resumo.

    - `dry_run=True`: só calcula o diff, não grava.
    - Cria heartbeats que existem no YAML e não no DB.
    - Alinha `enabled` e campos mutáveis do YAML sobre o DB.
    - Preserva `goal_id` do DB quando o YAML traz `null`.
    - Não deleta.
    """
    conn = _db(db_path)
    try:
        cfg = _load_yaml()
        if dry_run:
            # Resumo idempotente do diff, sem gravar.
            return {"dry_run": True, "total_in_yaml": len(cfg.heartbeats),
                    "pending_changes": diff(db_path=db_path, dry_run=True)}
        created, updated, unchanged = [], [], []
        now = _now_iso()
        for hb in cfg.heartbeats:
            row = conn.execute("SELECT * FROM heartbeats WHERE id=?", (hb.id,)).fetchone()
            if not row:
                conn.execute(
                    """INSERT INTO heartbeats
                       (id, agent, interval_seconds, max_turns, timeout_seconds,
                        lock_timeout_seconds, wake_triggers, enabled, goal_id,
                        required_secrets, decision_prompt, handler, source_plugin,
                        created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        hb.id, hb.agent, hb.interval_seconds, hb.max_turns,
                        hb.timeout_seconds, hb.lock_timeout_seconds,
                        json.dumps(list(hb.wake_triggers)), 1 if hb.enabled else 0,
                        hb.goal_id, json.dumps(list(hb.required_secrets)),
                        hb.decision_prompt, hb.handler, hb.source_plugin, now, now,
                    ),
                )
                created.append(hb.id)
                continue

            sets: list[str] = []
            params: list = []
            for field in _FIELDS:
                sets.append(f"{field}=?")
                params.append(_yaml_value(hb, field))
            sets.append("enabled=?")
            params.append(1 if hb.enabled else 0)
            # goal_id: só sobrescreve se YAML explicita
            if hb.goal_id is not None and row["goal_id"] != hb.goal_id:
                sets.append("goal_id=?")
                params.append(hb.goal_id)

            before = [row[f] for f in _FIELDS] + [row["enabled"]] + [row["goal_id"]]
            sets.append("updated_at=?")
            params.append(now)
            params.append(hb.id)

            # Detecta se há algo para mudar antes de gravar (idempotência honesta)
            if not _has_change(conn, hb, row):
                unchanged.append(hb.id)
                continue

            conn.execute(f"UPDATE heartbeats SET {', '.join(sets)} WHERE id=?", params)
            updated.append(hb.id)

        conn.commit()
        return {
            "dry_run": dry_run,
            "total_in_yaml": len(cfg.heartbeats),
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
        }
    finally:
        conn.close()


def _has_change(conn, hb, row) -> bool:
    """True se alguma mudança seria aplicada (evita UPDATE toco no nada)."""
    for field in _FIELDS:
        yval = _yaml_value(hb, field)
        dval = (row[field] or "[]") if field in ("wake_triggers", "required_secrets") else row[field]
        if dval != yval:
            return True
    if (1 if hb.enabled else 0) != (1 if row["enabled"] else 0):
        return True
    if hb.goal_id is not None and row["goal_id"] != hb.goal_id:
        return True
    return False


def run_reconcile_on_boot() -> dict:
    """Hook opcional para o boot do dispatcher/reloader alinhar DB→YAML.

    Loga o diff e aplica. Devolve False (sem exceção) se algo falhar — nunca
    derruba o boot. Env var HB_RECONCILE_ON_BOOT=0 desliga.
    """
    import os
    if os.environ.get("HB_RECONCILE_ON_BOOT", "1").lower() in ("0", "false", "no"):
        print("[hb_reconcile] disabled by HB_RECONCILE_ON_BOOT", flush=True)
        return {"skipped": True}
    try:
        changed = diff(dry_run=False)
        result = reconcile(dry_run=False)
        if changed:
            resumo = "; ".join(f"{d['id']}.{d['field']}: {d['from']}→{d['to']}" for d in changed[:40])
            print(f"[hb_reconcile] boot: {len(changed)} mudança(s) — {resumo}", flush=True)
        else:
            print("[hb_reconcile] boot: banco já alinhado ao YAML", flush=True)
        return result
    except Exception as exc:  # noqa: BLE001 — reconcile no boot nunca derruba o processo
        print(f"[hb_reconcile] boot FAILED (non-fatal): {exc}", flush=True)
        return {"error": str(exc)}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Reconciliar config/heartbeats.yaml -> DB")
    p.add_argument("--dry-run", action="store_true", help="só mostra o diff")
    args = p.parse_args()
    if args.dry_run:
        d = diff(dry_run=True)
        if not d:
            print("OK — banco já alinhado ao YAML.")
        else:
            for x in d:
                print(f"{x['id']:34} {x['field']:20} {x['from']} -> {x['to']}")
    else:
        r = reconcile(dry_run=False)
        print(json.dumps(r, ensure_ascii=False, indent=2))
