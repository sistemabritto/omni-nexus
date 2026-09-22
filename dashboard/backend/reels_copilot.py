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
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"
ARTIFACTS_DIR = WORKSPACE / "workspace" / "social" / "reels"

BRT = timezone(timedelta(hours=-3))


class ReelGenerationError(Exception):
    """Geração de roteiro falhou após esgotar o budget do motor resiliente.

    Lançada por `tick()` (não por `generate_reel`/`decide`/`revise_reel`) para o
    heartbeat_runner gravar status='fail' — visível ao ops-watchdog. Os demais
    callers tratam o dict {'ok': False, 'error': …} devolvido por generate_reel.
    """

OPENREPLY_VPS = os.environ.get("OPENREPLY_SSH_HOST", "")  # vazio = executa local (dashboard já roda na VPS)
OPENREPLY_DB_CONTAINER = "postgres_postgres"
OPENREPLY_WORKSPACE_ID = os.environ.get("OPENREPLY_WORKSPACE_ID", "cmtn8ppz700010jmsp15ul9s0")
OPENREPLY_INSTRAM_ID = os.environ.get("OPENREPLY_INSTRAM_ID", "cmtn8t74m00040jmsxi8dbbzo")
# 2026-09-22: conexão POSTGRES DIRETA pela rede interna do swarm. O container do
# dashboard NÃO tem nem `docker` nem `ssh` no PATH, então o caminho antigo
# (`sh -c "docker exec … psql"`) falhava sempre -> 3 campanhas 'failed' seguidas.
# Por DNS interno (`postgres_postgres:5432`) + psycopg2 (já no venv) dá.
OPENREPLY_DATABASE_URL = os.environ.get("OPENREPLY_DATABASE_URL", "").strip()
OPENREPLY_PG_HOST = os.environ.get("OPENREPLY_PG_HOST", "postgres_postgres")
OPENREPLY_PG_PORT = int(os.environ.get("OPENREPLY_PG_PORT", "5432"))
OPENREPLY_PG_USER = os.environ.get("OPENREPLY_PG_USER", "postgres")
OPENREPLY_PG_PASSWORD = os.environ.get("OPENREPLY_PG_PASSWORD", "")
OPENREPLY_PG_DB = os.environ.get("OPENREPLY_PG_DB", "openreply")

MIRROR_PLATFORMS = ("youtube", "tiktok")

# B (2026-09-22): se um reel em 'review' fica sem decisão deste tempo, o copilot
# manda UM lembrete no Telegram (dedup) em vez de correr o heartbeat 18x em silêncio.
# Se REELS_AUTO_ARCHIVE_PAST_REMINDER=1, arquiva o reel e já gera o próximo.
REVIEW_STALE_HOURS = float(os.environ.get("REELS_REVIEW_STALE_HOURS", "24"))
REELS_AUTO_ARCHIVE = os.environ.get("REELS_AUTO_ARCHIVE_PAST_REMINDER", "0").lower() in ("1", "true", "yes")
NAG_STATE_PATH = WORKSPACE / "workspace" / "reports" / "reels-copilot" / "nag_state.json"
GENERATION_FAIL_PATH = WORKSPACE / "workspace" / "reports" / "reels-copilot" / "gen_fail_state.json"
# 2026-09-22: gerações falhas repetidas (ex.: lock disputado por outros agentic
# runs) viravam 'success' mudo — o Felipe nunca sabia que o copilot não tinha
# roteiro novo pronto. Dedup: alerta UMA vez a cada janela, depois segue quieto
# mas ainda reporta o erro (o ops-watchdog enxerga falhas consecutivas).
GEN_FAIL_ALERT_COOLDOWN_HOURS = float(os.environ.get("REELS_GEN_FAIL_ALERT_HOURS", "12"))


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
    from provider_fallback import resilient_invoke

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
    # 2026-09-22: troca de invoke_with_fallback -> resilient_invoke. Antes, quando
    # outro agentic run segurava o lock do workspace ("workspace busy … held the
    # lock for 320.0s"), a chamada devolvia "busy" NAO-retryável e generate_reel
    # desistia na hora: o tick marcava success, não gravava reel, não mandava card —
    # e a esteira inteira parava em silêncio (reel 2 arquivou em 17:30 mas nunca
    # gerou o reel 3). resilient_invoke repete a cadeia enquanto houver vereda
    # (busy/timeout), com backoff, dentro de um budget que cabe no heartbeat.
    result = resilient_invoke(
        prompt=prompt,
        max_turns=6,
        timeout_seconds=300,
        agent="",
        routing_key="reels-copilot",
        retry_budget_seconds=780,
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


def _openreply_pg_connect():
    """Conexão psycopg2 direta ao Postgres compartilhado do OpenReply.

    Ordem: OPENREPLY_DATABASE_URL (completo) > OPENREPLY_PG_* host/port/user/
    password/db. Retorna None se não há senha configurada (evita conexão cega).
    """
    import psycopg2
    if OPENREPLY_DATABASE_URL:
        return psycopg2.connect(OPENREPLY_DATABASE_URL, connect_timeout=10)
    if not OPENREPLY_PG_PASSWORD:
        return None
    return psycopg2.connect(
        host=OPENREPLY_PG_HOST, port=OPENREPLY_PG_PORT,
        user=OPENREPLY_PG_USER, password=OPENREPLY_PG_PASSWORD,
        dbname=OPENREPLY_PG_DB, connect_timeout=10,
    )


def create_openreply_campaign(row: dict) -> dict:
    """Cria a campanha 'próximo reel' (pendingNextReel=true) — o worker do
    OpenReply amarra sozinho ao próximo reel publicado. Best-effort: falha de DB
    devolve status='failed' e a geração segue (não derruba o roteiro/card)."""
    keyword = f"{int(row['seq']):02d}"
    name = f"Reels Copilot {keyword} — próximo Reel"
    dm_message = f"Opa {{username}}! Aqui está a recompensa que você pediu: veja {row.get('bait_text') or 'o material completo'} 👇 {{link}}"
    public_reply = f"Aqui está! Confere {row.get('bait_text') or 'o guia'} que preparei p/ você 😉 @{{username}}"
    aid = _cuid_like()

    sql = (
        'INSERT INTO "Automation" ('
        'id, "workspaceId", "instagramAccountId", name, goal, "postId", "postUrl", '
        '"pendingNextReel", "matchAnyPost", keywords, "matchAnyWord", "dmTriggerEnabled", '
        '"dmMessage", "openingDmEnabled", "openingDmMessage", "openingDmButtonLabel", '
        '"linkButtonLabel", "requireFollow", "followPromptMessage", "followPromptButtonLabel", '
        '"followUpEnabled", "followUpMessage", "followUpDelayMinutes", '
        '"publicReplyEnabled", "publicReplyMessage", "publicReplyMessages", '
        '"isActive", "wholeWordMatch", "reportShareSlug", "reportShareEnabled", '
        '"createdAt", "updatedAt") '
        'VALUES (%s,%s,%s,%s,NULL,NULL,NULL,true,false,ARRAY[%s],false,true,'
        '%s,false,NULL,NULL,%s,'
        'false,NULL,NULL,false,NULL,0,true,NULL,ARRAY[%s],'
        'true,true,NULL,true,(now() AT TIME ZONE \'UTC\'),(now() AT TIME ZONE \'UTC\'))'
    )
    params = (aid, OPENREPLY_WORKSPACE_ID, OPENREPLY_INSTRAM_ID, name, keyword,
              dm_message, "Abrir o guia", public_reply)
    try:
        conn = _openreply_pg_connect()
        if conn is None:
            return {"ok": False, "status": "failed",
                    "error": "OpenReply Postgres não configurado (OPENREPLY_PG_PASSWORD / _DATABASE_URL)"}
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "status": "created", "automation_id": aid, "name": name, "keyword": keyword}
    except Exception as exc:  # noqa: BLE001 — campanha é best-effort
        return {"ok": False, "status": "failed", "error": str(exc)[:200]}


# ── Ficha de criativo (artefato) + card Magneto ───────────────────────────────


def _creative_html(row: dict) -> str:
    """Ficha de criativo — HTML auto-contido (padrão .claude/rules/artifacts.md):
    um arquivo só, CSS inline, tema claro/escuro. Sem texto que não cabe no card."""
    import html as _h

    esc = lambda v: _h.escape(str(v or ""))  # noqa: E731
    n = int(row["seq"])
    bait = int(row.get("bait_number") or 0) or 1
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>[C] Reel {n:03d} — {esc(row.get('headline'))}</title>
<style>
:root {{
  --bg:#fafafa; --fg:#1a1a2e; --muted:#6b6b7b; --line:#e6e6ef;
  --accent:#6366f1; --accent2:#8b5cf6; --card:#fff; --ok:#16a34a; --warn:#d97706;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0f0f1a; --fg:#ececf1; --muted:#8f8f9f; --line:#26263a;
    --accent:#818cf8; --accent2:#a78bfa; --card:#17172b; --ok:#4ade80; --warn:#fbbf24;
  }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); line-height:1.65;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
.wrap {{ max-width:820px; margin:0 auto; padding:44px 20px 88px; }}
.badge {{ display:inline-block; background:var(--accent); color:#fff; border-radius:999px;
  padding:3px 12px; font-size:.75rem; letter-spacing:.06em; text-transform:uppercase; margin-bottom:14px; }}
h1 {{ font-size:1.55rem; margin:0 0 6px; line-height:1.3; }}
.meta {{ color:var(--muted); font-size:.9rem; margin-bottom:26px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:18px 20px; margin-bottom:16px; }}
.card h2 {{ font-size:.8rem; text-transform:uppercase; letter-spacing:.08em;
  color:var(--muted); margin:0 0 8px; }}
.script {{ white-space:pre-wrap; font-size:.98rem; }}
.cta {{ color:var(--accent); font-weight:600; }}
.bait {{ display:flex; gap:14px; align-items:baseline; }}
.bait .num {{ font-size:2rem; font-weight:800; color:var(--accent2); min-width:44px; }}
.status {{ font-size:.85rem; padding:2px 10px; border-radius:6px; background:color-mix(in srgb, var(--ok) 15%, transparent); color:var(--ok); }}
.status.warn {{ background:color-mix(in srgb, var(--warn) 15%, transparent); color:var(--warn); }}
.footer {{ color:var(--muted); font-size:.8rem; margin-top:30px; border-top:1px solid var(--line); padding-top:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <span class="badge">Ficha de criativo · Reel {n:03d}</span>
  <h1>{esc(row.get('headline'))}</h1>
  <div class="meta">Tema: {esc(row.get('theme'))} · Funil: {esc(row.get('funnel_stage') or '?')} · Avatar: {esc(row.get('avatar') or '?')}</div>

  <div class="card"><h2>Hook falado</h2><div>{esc(row.get('hook_spoken'))}</div></div>
  <div class="card"><h2>Hook visual</h2><div>{esc(row.get('hook_visual'))}</div></div>
  <div class="card"><h2>Roteiro (~45s)</h2><div class="script">{esc(row.get('script_md'))}</div></div>
  <div class="card"><h2>CTA</h2><div class="cta">{esc(row.get('cta'))}</div></div>

  <div class="card">
    <h2>Isca do Desafio (01–21)</h2>
    <div class="bait"><span class="num">{bait:02d}</span><span>{esc(row.get('bait_text') or '—')}</span></div>
  </div>

  <div class="card">
    <h2>Campanha OpenReply</h2>
    <div>{"✅ Campanha ativa — gatilho «" + f"{n:02d}" + "» (comentário → DM)" if row.get("openreply_status") == "created" else "⚠️ Não criada automaticamente (" + esc(row.get("openreply_status") or "falha") + ") — ativar manual"}</div>
    <div style="margin-top:6px"><span class="status {'warn' if row.get('status') not in ('approved','review') else ''}">{esc(row.get('status') or '?').upper()}</span></div>
  </div>

  <div class="footer">Gerado pelo reels-copilot no OmniNexus · {esc(row.get('created_at', '')[:16])} BRT<br>ID: <code>{esc(row.get('id'))}</code></div>
</div>
</body>
</html>"""


def publish_creative_share(row: dict) -> str | None:
    """Gera a ficha de criativo em workspace/social/reels/ e devolve o link do
    share (reaproveita o share existente do caminho — regra artifacts.md).
    None se o API/token não estiver disponível (fallback p/ card completo)."""
    import urllib.request
    import urllib.error
    import urllib.parse

    n = int(row["seq"])
    path_rel = f"workspace/social/reels/{n:03d}-ficha-criativo.html"
    full = WORKSPACE / "workspace" / "social" / "reels" / f"{n:03d}-ficha-criativo.html"
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(_creative_html(row), encoding="utf-8")
    except OSError as exc:
        log.warning("reel %d: não gravou ficha (%s)", n, exc)
        return None

    base_url = os.environ.get("EVONEXUS_API_URL", "").strip().rstrip("/")
    token = os.environ.get("DASHBOARD_API_TOKEN", "").strip()
    if not base_url or not token:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def _req(method: str, url: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={**headers, **({"Content-Type": "application/json"} if payload is not None else {})})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        try:
            existing = _req("GET", f"{base_url}/api/shares/by-path?path={urllib.parse.quote(path_rel)}")
            url = existing.get("url") if isinstance(existing, dict) and existing.get("url") else None
            if url:
                log.info("reel %d: ficha reusing share existente", n)
                return url
        except urllib.error.HTTPError:
            pass  # share ainda não existe — cria abaixo
        share = _req("POST", f"{base_url}/api/shares", {"path": path_rel, "expires_in": None})
        return share.get("url")
    except Exception as exc:  # noqa: BLE001 — sem link não é fim do mundo (fallback no card)
        log.warning("reel %d: share não criado (%s)", n, exc)
        return None


def build_card(row: dict, share_url: str | None = None) -> str:
    from notifications import _esc

    n = int(row["seq"])
    marker = f"#reel:{row['id']}"
    lines = [f"🎬 <b>Reel {n:03d} — pronto p/ gravar</b>"]
    if share_url:
        # Card curto: a ficha completa mora no link (robusto, sem estourar os
        # 4096 chars nem depender de HTML impecável). O marcador #reel:<id>
        # mantém a ponte de decisão por reply funcionando.
        lines += [
            "",
            _esc(str(row["headline"])),
            "",
            f"📄 <a href=\"{_esc(share_url)}\">Abrir ficha de criativo</a>",
            "",
            f"Responda por ÁUDIO: aprovou / não + motivo / ajuste.",
            f"Texto: {marker} ok | {marker} nao | {marker} ajuste: {_esc('<o que mudar>')}",
        ]
        return "\n".join(lines)

    # Fallback: sem link (API fora) — card completo com texto sanado p/ HTML.
    lines += [
        f"TEMA: {_esc(str(row['theme']))}",
        f"FUNIL: {str(row.get('funnel_stage') or '?')} · AVATAR: {_esc(str(row.get('avatar') or '?'))}",
        "",
        f"<b>HEADLINE:</b> {_esc(str(row['headline']))}",
        f"<b>HOOK FALADO:</b> {_esc(str(row['hook_spoken']))}",
        f"<b>HOOK VISUAL:</b> {_esc(str(row['hook_visual']))}",
        "",
        f"<b>ROTEIRO (~45s):</b>\n{_esc(str(row['script_md']))[:1500]}",
        "",
        f"<b>CTA:</b> {_esc(str(row['cta']))}",
        f"<b>ISCA {int(row['bait_number'] or 0):02d}:</b> {_esc(str(row.get('bait_text') or ''))}",
        "",
    ]
    if row.get("openreply_status") == "created":
        lines.append(f"✅ OpenReply: campanha ativa, gatilho \"{n:02d}\" (comentário → DM)")
    else:
        lines.append(f"⚠️ OpenReply: não criou automaticamente ({row.get('openreply_status')}) — ativar manual")
    lines.append("— responda por ÁUDIO: aprovou / não + motivo / ajuste")
    lines.append(f"Texto: {marker} ok | {marker} nao | {marker} ajuste: {_esc('<o que mudar>')}")
    card = "\n".join(lines)
    # Telegram aceita 4096 chars; sem o link a ficha inteira vem aqui — corta o
    # roteiro antes de estourar (a ficha completa segue no .md do artefato).
    if len(card) > 3950:
        excess = len(card) - 3950
        idx = next((i for i, l in enumerate(lines) if l.startswith("<b>ROTEIRO")), -1)
        if idx >= 0:
            body = lines[idx]
            keep = max(0, len(body) - excess - 3)
            lines[idx] = body[:keep] + "… [cortado — veja arquivo no workspace]"
        card = "\n".join(lines)
    return card[:4096]


def send_reel_card(row: dict) -> bool:
    try:
        from notifications import send_telegram_alert
        share_url = publish_creative_share(row)
        return send_telegram_alert(build_card(row, share_url))
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


def _load_nag_state() -> dict:
    try:
        return json.loads(NAG_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_nag_state(state: dict) -> None:
    NAG_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = NAG_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(NAG_STATE_PATH)


def _handle_stale_review(row: dict) -> dict | None:
    """Se um reel 'review' ficou sem decisão além de REVIEW_STALE_HOURS, devolve um
    resultado de tick (lembrete único / auto-arquivo). None se ainda não chegou na hora.

    Sem isso o heartbeat roda a cada 3h, vê o mesmo reel pendente e só devolve
    'generated:False' — 18 runs 'success' que são silêncio, e o Felipe não sabe
    que o copilot tá esperando o dele. O lembrete é DEDUP por reel.id (uma vez).
    """
    if row["status"] != "review":
        return None
    age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(
        row["updated_at"].replace("Z", "+00:00"))).total_seconds() / 3600
    if age_h < REVIEW_STALE_HOURS:
        return None
    seq = int(row["seq"])
    state = _load_nag_state()
    last_nag = state.get(str(row["id"]), {}).get("at")
    if last_nag:
        # já lembrou — agora ou arquiva (se ligado) ou fica quieto
        if REELS_AUTO_ARCHIVE:
            conn = _connect()
            try:
                conn.execute("UPDATE reels SET status='rejected', rejected_reason="
                             "'arquivado: sem decisão além do prazo, copilot seguiu adiante', updated_at=? WHERE id=?",
                             (_now_iso(), row["id"]))
                conn.commit()
            finally:
                conn.close()
            kicked = kick_next_theme("anterior arquivado por inatividade")
            return {"generated": bool(kicked.get("ok")), "auto_archived": seq,
                    "reason": f"reel {seq:03d} ficou >{REVIEW_STALE_HOURS:.0f}h sem decisão; arquivado e fila seguiu"}
        return {"generated": False, "reason": f"reel {seq:03d} já recebeu lembrete de inatividade"}
    # primeiro lembrete deste reel
    from notifications import send_telegram_alert
    from notifications import _esc
    card = (
        f"⏰ <b>Copilot de reels</b> — reel <b>{seq:03d}</b> te espera há {age_h:.0f}h.\n"
        f"<i>{_esc(row['theme'])}</i>\n\n"
        f"Responde por áudio ou <code>#reel:{seq:03d} aprova|rejeita|revisa</code>."
    )
    ok = send_telegram_alert(card)
    state[str(row["id"])] = {"at": _now_iso(), "seq": seq, "reminded": bool(ok)}
    _save_nag_state(state)
    return {"generated": False, "reason": f"reel {seq:03d} >{REVIEW_STALE_HOURS:.0f}h em review; lembrete enviado={ok}"}


def _load_gen_fail_state() -> dict:
    try:
        return json.loads(GENERATION_FAIL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_gen_fail_state(state: dict) -> None:
    GENERATION_FAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GENERATION_FAIL_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(GENERATION_FAIL_PATH)


def _report_generation_fail(reason: str) -> bool:
    """Superficia uma geração falhada no Magneto — DEDUP por cooldown.

    Antes era silêncio total: tick devolvia {'generated': False, 'reason': …} e o
    heartbeat_runner gravava status='success' (o handler não lançou exceção), então
    nem o Magneto nem o ops-watchdog viam que a esteira tinha parado. Aqui enviamos
    UM alerta por janela de GEN_FAIL_ALERT_COOLDOWN_HOURS; dentro do cooldown só
    incrementamos o contador (sem spam a cada 3h). Retorna True se enviou o card.
    """
    state = _load_gen_fail_state()
    cur = state.get("current") or {}
    now = datetime.now(timezone.utc)
    # Falha de MESMA natureza em janela curta -> dedup (só conta).
    try:
        last = datetime.fromisoformat(cur["at"].replace("Z", "+00:00")) if cur.get("at") else None
    except ValueError:
        last = None
    within_cooldown = (last is not None
                       and (now - last).total_seconds() < GEN_FAIL_ALERT_COOLDOWN_HOURS * 3600)
    streak = int(cur.get("streak", 0)) + 1
    sent = False
    if not within_cooldown:
        try:
            from notifications import send_telegram_alert
            card = (
                f"⚠️ <b>Copilot de reels</b> — não consegui gerar roteiro novo.\n"
                f"<i>{_reason_brief(reason)}</i>\n\n"
                f"Costuma ser o lock do workspace disputado por outros agentes. "
                f"Vou tentar de novo na próxima rodada; se persistir {streak}x seguidas, "
                f"abro ticket."
            )
            sent = bool(send_telegram_alert(card))
        except Exception as exc:  # noqa: BLE001 — alerta nunca derruba o tick
            log.warning("reels_copilot gen-fail alert: %s", exc)
        cur = {"at": _now_iso(), "streak": streak, "reason": reason[:200]}
        _save_gen_fail_state({"current": cur})
    else:
        cur["streak"] = streak
        _save_gen_fail_state({"current": cur})
    log.info("reels_copilot gen-fail reported=%s streak=%d reason=%s", sent, streak, reason[:120])
    return sent


def _reason_brief(reason: str) -> str:
    r = (reason or "").strip().replace("\n", " ")
    return r[:180]


def tick() -> dict:
    """Handler do heartbeat: garante 1 reel em voo (gera se a fila estiver vazia)."""
    if not DB_PATH.exists():
        return {"error": "db not found", "generated": False}
    conn = _connect()
    try:
        _ensure_reels_table(conn)
        in_flight = get_in_flight(conn)
    finally:
        conn.close()
    if in_flight:
        stale = _handle_stale_review(dict(in_flight))
        if stale is not None:
            return stale
        return {"generated": False, "reason": "já há reel em voo — 1 de cada vez"}
    res = generate_reel()
    if res.get("ok"):
        # reel novo começou — zera contador de falhas + lembrete pendente de outros
        _save_gen_fail_state({})
        return {"generated": True, "seq": int(res["reel"]["seq"]),
                "campaign": res.get("openreply", {}).get("status"), "card_sent": res.get("card_sent")}
    # Falha real de geração: NÃO fica em silêncio. (1) alerta no Magneto com
    # dedup por cooldown, (2) levanta exceção para o heartbeat_runner gravar
    # status='fail' — assim o ops-watchdog detecta 2+ fails consecutivos e abre
    # ticket p/ hawk-debugger (self-heal P5) em vez da esteira morrer muda.
    reason = res.get("error") or "desconhecido"
    _report_generation_fail(reason)
    raise ReelGenerationError(f"reels-copilot: geração falhou ({reason})")
