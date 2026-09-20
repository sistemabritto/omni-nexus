"""reels_copilot — o coprodutor de reels do Magneto (P1 do [C]revamp-cockpit-reels-multitenant.md).

Ciclo evergreen, MÁXIMO 1 reel em voo: cada tick gera UM roteiro completo
(tema→headline→hooks→roteiro humanizado→CTA+isca) quando não há reel aguardando,
cria a campanha no OpenReply, manda o card no Telegram para aprovação por
áudio/texto do Felipe, espelha no Postiz (Shorts+TikTok) quando ele posta.

Peças:
- `tick()` (handler in-process do heartbeat reels-copilot): garante 1 reel em voo
- `generate_reel(theme_hint)` : chama o agente reels-copilot via invoke_with_fallback
  (combo CX-WORKHORSE pelo Bloco F), valida o JSON e grava na tabela `reels`
- `create_openreply_campaign(row)` : INSERT no Postgres compartilhado via SSH
  (mesmo caminho da skill custom-int-openreply; best-effort)
- `build_card(row)` / `_send_card` : card de aprovação no Magneto (HTML)
- `decide(reel_id, decision, feedback)` : chamado pela bridge do bot
  (voice note transcrita pelo Groq ou texto #reel:<id>)
- `mirror_posted(reel_id)` : `/postei` → Postiz YouTube Shorts + TikTok
- `pipeline_summary()` : usado por /reels e pelo relatório diário

A tabela `reels` é criada via db.create_all (models.Reel) + ensure em app.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"
ARTIFACTS_DIR = WORKSPACE / "workspace" / "social" / "reels"

BRT = timezone(timedelta(hours=-3))

OPENREPLY_VPS = os.environ.get("OPENREPLY_SSH_HOST", "")  # vazio = executa local (dashboard já roda na VPS)
OPENREPLY_DB_CONTAINER = "postgres_postgres"
OPENREPLY_WORKSPACE_ID = os.environ.get("OPENREPLY_WORKSPACE_ID", "cmtn8ppz700010jmsp15ul9s0")
OPENREPLY_INSTRAM_ID = os.environ.get("OPENREPLY_INSTRAM_ID", "cmtn8t74m00040jmsxi8dbbzo")

MIRROR_PLATFORMS = ("youtube", "tiktok")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ── Banco local ───────────────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_reels_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reels (
            id TEXT PRIMARY KEY,
            seq INTEGER,
            theme TEXT NOT NULL,
            avatar TEXT,
            funnel_stage TEXT,
            headline TEXT,
            hook_spoken TEXT,
            hook_visual TEXT,
            script_md TEXT,
            cta TEXT,
            bait_number INTEGER,
            bait_text TEXT,
            openreply_campaign_id TEXT,
            openreply_status TEXT DEFAULT 'pending',
            postiz_jobs_json TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            rejected_reason TEXT,
            artifact_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.commit()


def get_in_flight(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Reel em voo: aguardando aprovação (review) ou postado e ainda sem espelho."""
    return conn.execute(
        """SELECT * FROM reels WHERE status IN ('draft','review','approved','posted')
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()


def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reels ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()


# ── Geração (LLM) ────────────────────────────────────────────────────────────

_REEL_SCHEMA_HINT = (
    "Responda SOMENTE com JSON válido, sem markdown, com exatamente estas chaves:\n"
    '{"theme": str, "avatar": str, "funnel_stage": "atrair|doutrinar|converter",'
    ' "headline": str, "hook_spoken": str, "hook_visual": str,'
    ' "script_md": str (roteiro completo ~45s, humanizado, frases curtas),'
    ' "cta": str, "bait_number": int (1-21), "bait_text": str}'
)

_REQUIRED = ("theme", "headline", "hook_spoken", "hook_visual", "script_md", "cta")


def _extract_text(raw: str) -> str:
    """Normaliza o output do LLM para texto.

    O Drael/opencode emite NDJSON (um evento por linha: step_start, text, ...);
    Claude/Codex devolvem um envelope único. Se o output tem múltiplas linhas que
    parseiam como JSON de evento, extrai a resposta real dos eventos `text`.
    """
    from provider_fallback import _parse_opencode_ndjson

    lines = [l for l in raw.splitlines() if l.strip()]
    # NDJSON? duas+ linhas que são eventos de opencode/claude (têm "type")
    events = 0
    for l in lines[:20]:
        try:
            ev = json.loads(l)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(ev, dict) and "type" in ev:
            events += 1
    if events >= 2:
        parsed = _parse_opencode_ndjson(raw)
        if parsed.get("text"):
            return parsed["text"]
    return raw


def _parse_llm_json(raw: str) -> dict:
    text = _extract_text(raw).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError(f"sem JSON no output ({len(text)} chars): {text[:120]!r}")
    # raw_decode lê o PRIMEIRO objeto JSON completo a partir de { e ignora o
    # resto (o LLM às vezes devolve "Aqui está o roteiro: {…} (pronto!)" ou um
    # segundo objeto solto — json.loads no slice até o último } dava "Extra data").
    try:
        data, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no output: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON do roteiro não é um objeto")
    missing = [k for k in _REQUIRED if not str(data.get(k) or "").strip()]
    if missing:
        raise ValueError(f"campos faltando: {missing}")
    try:
        data["bait_number"] = int(data.get("bait_number") or 0) % 21 + 1
    except (TypeError, ValueError):
        data["bait_number"] = 1
    return data


def generate_reel(theme_hint: str | None = None) -> dict:
    """Gera UM roteiro completo, grava como draft/review e devolve a row.

    theme_hint: tema opcional imposto pelo humano (/reel <tema> ou rejeição com
    crítica). Sem hint, o próprio LLM escolhe a partir da matriz de temas da skill.
    """
    from provider_fallback import invoke_with_fallback

    hint = f"\nTema imposto pelo criador (OBRIGATÓRIO usá-lo como base): {theme_hint}\n" if theme_hint else ""
    prompt = (
        "Você é o reels-copilot do Sistema Britto. Crie UM roteiro de Reels pronto "
        "para gravar, seguindo seus protocolos: fase de funil (social-editorial-strategy), "
        "headline no padrão protocolo (9 hooks Omni Nexus), hook falado e visual "
        "(social-hook-bank), estrutura de roteiro (social-reels-scripts, ~45s), "
        "pass de humanizer (24 padrões anti-AI) e isca numerada 01-21 do Desafio "
        "(mkt-iscas-desafio) compatível com a fase do funil."
        + hint
        + "\n\n" + _REEL_SCHEMA_HINT
    )
    result = invoke_with_fallback(
        prompt=prompt,
        max_turns=6,
        timeout_seconds=300,
        agent="",
        routing_key="reels-copilot",
    )
    if result.get("status") != "success":
        return {"ok": False, "error": f"LLM falhou: {result.get('error') or result.get('status')}"}

    data = _parse_llm_json(result.get("output") or result.get("result") or "")

    conn = _connect()
    try:
        _ensure_reels_table(conn)
        last = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM reels").fetchone()[0]
        rid = str(uuid.uuid4())
        now = _now_iso()
        conn.execute(
            """INSERT INTO reels (id, seq, theme, avatar, funnel_stage, headline,
               hook_spoken, hook_visual, script_md, cta, bait_number, bait_text,
               status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'review', ?, ?)""",
            (rid, last, data["theme"], data.get("avatar"), data.get("funnel_stage"),
             data["headline"], data["hook_spoken"], data["hook_visual"], data["script_md"],
             data["cta"], data["bait_number"], data.get("bait_text"), now, now),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM reels WHERE id=?", (rid,)).fetchone())
    finally:
        conn.close()

    _write_artifact(row)

    # Campanha OpenReply (best-effort — falha não derruba a geração)
    camp = create_openreply_campaign(row)
    conn = _connect()
    try:
        conn.execute(
            "UPDATE reels SET openreply_status=?, openreply_campaign_id=?, updated_at=? WHERE id=?",
            (camp.get("status", "failed"), camp.get("automation_id"), _now_iso(), rid),
        )
        conn.commit()
    finally:
        conn.close()

    sent = send_reel_card(row)
    log.info("reels_copilot gerado seq=%d status=campaign:%s card=%s", row["seq"], camp.get("status"), sent)
    return {"ok": True, "reel": row, "openreply": camp, "card_sent": sent}


def _write_artifact(row: dict) -> None:
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS_DIR / f"{int(row['seq']):03d}-{re.sub(r'[^a-z0-9]+', '-', row['theme'].lower()).strip('-')[:48] or 'reel'}.md"
        path.write_text(
            f"# Reel {int(row['seq']):03d} — {row['theme']}\n\n"
            f"- Funil: {row.get('funnel_stage') or '?'} · Avatar: {row.get('avatar') or '?'}\n"
            f"- Isca: {int(row.get('bait_number') or 0):02d} — {row.get('bait_text') or ''}\n"
            f"- OpenReply: {row.get('openreply_campaign_id') or 'pendente'} ({row.get('openreply_status')})\n\n"
            f"## Headline\n{row['headline']}\n\n## Hook falado\n{row['hook_spoken']}\n\n"
            f"## Hook visual\n{row['hook_visual']}\n\n## Roteiro\n{row['script_md']}\n\n## CTA\n{row['cta']}\n",
            encoding="utf-8",
        )
        row["artifact_path"] = str(path.relative_to(WORKSPACE))
    except Exception as exc:  # noqa: BLE001
        log.warning("reels_copilot artifact fail: %s", exc)


# ── OpenReply (SSH → Postgres compartilhado) ─────────────────────────────────


def _cuid_like(prefix_len: int = 25) -> str:
    import base64
    import random
    import string
    import time
    ts = format(int(time.time() * 1000), "x")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=prefix_len - 1 - len(ts)))
    return ("c" + ts + rand)[:prefix_len]


def create_openreply_campaign(row: dict) -> dict:
    """Cria a campanha 'próximo reel' (pendingNextReel=true) — o worker do
    OpenReply amarra sozinho ao próximo reel publicado. Best-effort: SSH/Postgres
    indisponível devolve status='failed' e a geração segue."""
    keyword = f"{int(row['seq']):02d}"
    name = f"Reels Copilot {keyword} — próximo Reel"
    dm_message = f"Opa {{username}}! Aqui está a recompensa que você pediu: veja {row['bait_text'] or 'o material completo'} 👇 {{link}}"
    public_reply = f"Aqui está! Confere {row['bait_text'] or 'o guia'} que preparei p/ você 😉 @{{username}}"
    aid = _cuid_like()

    sql = f"""INSERT INTO "Automation" (
      id, "workspaceId", "instagramAccountId", name, goal, "postId", "postUrl",
      "pendingNextReel", "matchAnyPost", keywords, "matchAnyWord", "dmTriggerEnabled",
      "dmMessage", "openingDmEnabled", "openingDmMessage", "openingDmButtonLabel",
      "linkButtonLabel", "requireFollow", "followPromptMessage", "followPromptButtonLabel",
      "followUpEnabled", "followUpMessage", "followUpDelayMinutes",
      "publicReplyEnabled", "publicReplyMessage", "publicReplyMessages",
      "isActive", "wholeWordMatch", "reportShareSlug", "reportShareEnabled",
      "createdAt", "updatedAt")
    VALUES ('{aid}', '{OPENREPLY_WORKSPACE_ID}', '{OPENREPLY_INSTRAM_ID}',
      '{name}', NULL, NULL, NULL, true, false, ARRAY['{keyword}'], false, true,
      '{dm_message.replace(chr(39), chr(39)*2)}', false, NULL, NULL, 'Abrir o guia',
      false, NULL, NULL, false, NULL, 0, true, NULL, ARRAY['{public_reply.replace(chr(39), chr(39)*2)}'],
      true, true, NULL, true, (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC'));"""

    psql_cmd = (
        f"docker exec $(docker ps -q -f name={OPENREPLY_DB_CONTAINER}) psql -U postgres "
        f"-d openreply -c \"SET search_path=public; {sql.replace(chr(10), ' ')}\""
    )
    try:
        if OPENREPLY_VPS:
            cmd = ["ssh", OPENREPLY_VPS, psql_cmd]
        else:
            # Dashboard já roda na própria VPS — executa o docker exec direto, sem SSH.
            cmd = ["sh", "-c", psql_cmd]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0 and "INSERT" in proc.stdout:
            return {"ok": True, "status": "created", "automation_id": aid, "name": name, "keyword": keyword}
        return {"ok": False, "status": "failed", "error": (proc.stderr or proc.stdout)[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "failed", "error": str(exc)[:200]}


# ── Card Magneto ─────────────────────────────────────────────────────────────


def build_card(row: dict) -> str:
    from notifications import _esc

    n = int(row["seq"])
    lines = [
        f"🎬 <b>Reel {n:03d} — pronto p/ gravar</b>",
        f"TEMA: {_esc(str(row['theme']))}",
        f"FUNIL: {str(row.get('funnel_stage') or '?')} · AVATAR: {_esc(str(row.get('avatar') or '?'))}",
        f"",
        f"<b>HEADLINE:</b> {_esc(str(row['headline']))}",
        f"<b>HOOK FALADO:</b> {_esc(str(row['hook_spoken']))}",
        f"<b>HOOK VISUAL:</b> {_esc(str(row['hook_visual']))}",
        f"",
        f"<b>ROTEIRO (~45s):</b>\n{_esc(str(row['script_md']))[:1500]}",
        f"",
        f"<b>CTA:</b> {_esc(str(row['cta']))}",
        f"<b>ISCA {int(row['bait_number'] or 0):02d}:</b> {_esc(str(row.get('bait_text') or ''))}",
        f"",
    ]
    if row.get("openreply_status") == "created":
        lines.append(f"✅ OpenReply: campanha ativa, gatilho \"{n:02d}\" (comentário → DM)")
    else:
        lines.append(f"⚠️ OpenReply: não criou automaticamente ({row.get('openreply_status')}) — ativar manual")
    lines.append("— responda por ÁUDIO: aprovou / não + motivo / ajuste")
    lines.append(f"Texto: #reel:{row['id']} ok | #reel:{row['id']} nao | #reel:{row['id']} ajuste:<o que mudar>")
    return "\n".join(lines)


def send_reel_card(row: dict) -> bool:
    try:
        from notifications import send_telegram_alert
        return send_telegram_alert(build_card(row))
    except Exception as exc:  # noqa: BLE001
        log.warning("reels_copilot card fail: %s", exc)
        return False


# ── Decisão (bridge do bot) ──────────────────────────────────────────────────


def decide(reel_id: str, decision: str, feedback: str = "") -> dict:
    """'approve' | 'reject' | 'revise'. Sem DB (bot não monta o volume em VPS? sim —
    o bot roda NA VPS no mesmo host; usa o arquivo direto via file lock, padrão
    do próprio bot com offset state)."""
    if not DB_PATH.exists():
        return {"ok": False, "error": "db não acessível"}
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        row = conn.execute("SELECT * FROM reels WHERE id=? OR seq=?",
                           (reel_id, _try_int(reel_id))).fetchone()
        if not row:
            return {"ok": False, "error": f"reel {reel_id} não encontrado"}
        row = dict(row)
        now = _now_iso()
        if decision == "approve":
            conn.execute("UPDATE reels SET status='approved', rejected_reason=NULL, updated_at=? WHERE id=?", (now, row["id"]))
            msg = f"✅ Reel {int(row['seq']):03d} aprovado! Grave e poste. Depois mande /postei {int(row['seq']):03d}"
        elif decision == "reject":
            conn.execute("UPDATE reels SET status='rejected', rejected_reason=?, updated_at=? WHERE id=?",
                         (feedback or None, now, row["id"]))
            msg = f"❌ Reel {int(row['seq']):03d} arquivado. Um novo tema entra na fila agora."
            kicked = kick_next_theme(feedback or "tema anterior rejeitado")
            msg += "" if kicked.get("ok") else f" (fila: {kicked.get('error','?')})"
        elif decision == "revise":
            conn.execute("UPDATE reels SET status='draft', rejected_reason=?, updated_at=? WHERE id=?",
                         (feedback or None, now, row["id"]))
            msg = f"✏️ Ajuste anotado no reel {int(row['seq']):03d}: {feedback[:120]}"
            res = revise_reel(row["id"], feedback)
            msg += f" Rascunho revisado enviado novamente.{' ✅' if res.get('ok') else ' ❌ ' + str(res.get('error','?'))[:100]}"
        else:
            return {"ok": False, "error": f"decisão desconhecida: {decision}"}
        conn.commit()
        return {"ok": True, "toast": msg, "reel_id": row["id"], "seq": int(row["seq"])}
    finally:
        conn.close()


def _try_int(s: str) -> int:
    try:
        return int(str(s).split(":")[-1])
    except (TypeError, ValueError):
        return -1


def kick_next_theme(context: str) -> dict:
    """Após rejeição: gera o próximo reel imediatamente (com a crítica como hint)."""
    try:
        return generate_reel(theme_hint=f"Anterior foi REJEITADO pelo criador. Lição: {context}. Escolha um ângulo DIFERENTE.")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def revise_reel(reel_id: str, feedback: str) -> dict:
    """Regenera o roteiro do mesmo tema incorporando a crítica, novo card."""
    conn = _connect()
    try:
        row = dict(conn.execute("SELECT * FROM reels WHERE id=?", (reel_id,)).fetchone() or {})
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "reel não encontrado"}
    try:
        res = generate_reel(theme_hint=f"MESMO TEMA: {row['theme']}. CRÍTICA do criador a incorporar: {feedback}")
        if res.get("ok"):
            conn = _connect()
            try:
                conn.execute("DELETE FROM reels WHERE id=?", (reel_id,))
                conn.commit()
            finally:
                conn.close()
        return res
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


# ── /postei → espelhamento Postiz ────────────────────────────────────────────


def mirror_posted(reel_id: str, ig_url: str | None = None) -> dict:
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        row = conn.execute("SELECT * FROM reels WHERE id=? OR seq=?",
                           (reel_id, _try_int(reel_id))).fetchone()
        if not row:
            return {"ok": False, "error": f"reel {reel_id} não encontrado"}
        row = dict(row)
        conn.execute("UPDATE reels SET status='mirrored', updated_at=? WHERE id=?", (_now_iso(), row["id"]))
        conn.commit()
    finally:
        conn.close()

    jobs = {}
    if ig_url:
        try:
            from postiz_client import PostizClient, build_youtube_payload, build_tiktok_payload
            client = PostizClient.from_env()
            if client is None:
                return {"ok": True, "skipped": "Postiz não configurado (POSTIZ_URL/API_KEY)", "jobs": jobs, "seq": int(row["seq"])}
            now_iso = _now_iso()
            for platform in MIRROR_PLATFORMS:
                iid = (client.integration_ids or {}).get(platform)
                if not iid:
                    jobs[platform] = {"error": f"POSTIZ_INTEGRATION_{platform.upper()}_ID ausente"}
                    continue
                caption = f"{row['headline']}\n\n{row['cta']}\n\n#sistemabritto #ia"
                try:
                    if platform == "youtube":
                        settings = build_youtube_payload(title=row["headline"][:100])
                    else:
                        settings = build_tiktok_payload(privacy_level="PUBLIC_TO_EVERYONE")
                    posts = client.create_draft(integration_id=iid, content=caption,
                                                media=[{"url": ig_url}], settings=settings,
                                                now_iso_utc=now_iso)
                    jobs[platform] = {"drafts": len(posts)}
                except Exception as exc:  # noqa: BLE001
                    jobs[platform] = {"error": str(exc)[:160]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": True, "skipped": f"espelhamento indisponível: {exc}", "jobs": {}, "seq": int(row["seq"])}

    conn = _connect()
    try:
        conn.execute("UPDATE reels SET postiz_jobs_json=?, status='mirrored', updated_at=? WHERE id=?",
                     (json.dumps(jobs, ensure_ascii=False) if jobs else None, _now_iso(), row["id"]))
        conn.commit()
    finally:
        conn.close()
    done = sum(1 for v in jobs.values() if isinstance(v, dict) and not v.get("error"))
    return {"ok": True, "seq": int(row["seq"]), "mirrored": done, "of": len(MIRROR_PLATFORMS), "jobs": jobs}


# ── Pipeline (/reels + relatório diário) ─────────────────────────────────────


def pipeline_summary() -> str:
    if not DB_PATH.exists():
        return "🎬 Reels: banco local indisponível"
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        rows = list_recent(conn, limit=12)
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        in_flight = get_in_flight(conn)
    finally:
        conn.close()
    line = "🎬 Reels: "
    parts = []
    for st in ("draft", "review", "approved", "posted", "mirrored", "rejected", "done"):
        if counts.get(st):
            parts.append(f"{counts[st]} {st}")
    line += " · ".join(parts) if parts else "nenhum gerado ainda"
    if in_flight:
        line += f" | em voo: {int(in_flight['seq']):03d} ({in_flight['status']})"
    return line


def tick() -> dict:
    """Handler do heartbeat: garante 1 reel em voo (gera se a fila estiver vazia)."""
    if not DB_PATH.exists():
        return {"error": "db not found", "generated": False}
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        if get_in_flight(conn):
            return {"generated": False, "reason": "já há reel em voo — 1 de cada vez"}
    finally:
        conn.close()
    res = generate_reel()
    if res.get("ok"):
        return {"generated": True, "seq": int(res["reel"]["seq"]),
                "campaign": res["openreply"].get("status"), "card_sent": res["card_sent"]}
    return {"generated": False, "reason": res.get("error")}
