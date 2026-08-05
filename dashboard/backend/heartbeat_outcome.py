"""Interpret an agent's heartbeat result and apply it to the kanban.

The old model fired "✅ Heartbeat OK" for every successful run, including
no-op skips — pure noise. This module replaces that with outcome-driven
behaviour: the agent ends its run with a structured JSON block describing what
it did, and we (1) move the ticket on the board, (2) record a comment + activity,
and (3) decide whether anything is worth telling Felipe on Telegram.

Agent output contract (the agent appends this JSON to its final message):

    {
      "action": "work" | "skip" | "blocked",
      "ticket_id": "<id or null>",
      "result": "<one-line natural-language summary of what was done>",
      "new_status": "in_progress" | "review" | "resolved" | "blocked" | null,
      "blocked_reason": "<why it is stuck, if blocked>",
      "needs": "<what Felipe must provide to unblock: data, credential, decision>"
    }

Notification policy (decided with Felipe 2026-06-17):
  - action=skip  → silent (nothing to report)
  - action=work  → notify the *result* (not tokens/cost)
  - action=blocked → notify, because Felipe needs to intervene
  - unparseable / no JSON → silent (no more "heartbeat ok" spam)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Timezone used only to render a scheduled publish time in the Telegram
# approval card. Everything is stored and sent to Postiz in UTC; this is
# presentation only, so Felipe reads "18/08 09:00" and not a UTC offset.
PUBLISH_DISPLAY_TZ = os.environ.get("WORKSPACE_TIMEZONE") or "America/Sao_Paulo"
try:
    _PUBLISH_DISPLAY_ZONE = ZoneInfo(PUBLISH_DISPLAY_TZ)
except Exception:  # bad/absent tzdata must never break the approval card
    PUBLISH_DISPLAY_TZ = "UTC"
    _PUBLISH_DISPLAY_ZONE = timezone.utc

# Valid ticket states (see .claude/rules/tickets.md)
_VALID_STATUS = {"open", "in_progress", "blocked", "review", "resolved", "closed"}
_STATUS_ALIASES = {
    "done": "resolved",
    "complete": "resolved",
    "completed": "resolved",
    "finished": "resolved",
    "in progress": "in_progress",
    "inprogress": "in_progress",
    "review_needed": "review",
    "needs_review": "review",
}


def _now_iso() -> str:
    """Timestamp no formato do resto do sistema: sufixo Z, sem offset.

    Era `isoformat()`, que produz `+00:00`. Duas linhas adjacentes gravavam
    formatos diferentes na MESMA linha de `pending_approvals` — `created_at`
    com `+00:00`, `expires_at` com `Z` —, e `ticket_janitor._parse_iso` faz
    `strptime(ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f")`, que levanta
    `ValueError: unconverted data remains: +00:00`. O erro caía num `continue`
    e os re-nudges de 2h e 4h nunca aconteceram para nenhuma aprovação criada
    pelo heartbeat — que é o caminho real. A expiração de 8h funcionava só
    porque lia o outro campo.

    Tornar o parser tolerante trataria o sintoma e deixaria dois formatos
    convivendo no banco. `routes/goals.py`, `routes/tickets.py`,
    `routes/approvals.py` e `ticket_janitor.py` já usavam este; era este
    módulo que estava fora do padrão.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _normalize_status(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().lower()
    s = _STATUS_ALIASES.get(s, s)
    return s if s in _VALID_STATUS else None


def _unwrap_provider_output(text: str) -> str:
    """Unwrap the CLI/provider JSON envelope to get the assistant's actual text.

    step7 returns the raw CLI output, which for `--output-format json` is an
    envelope like {"type":"result","result":"<assistant text>","usage":{…}}.
    The agent's outcome JSON lives INSIDE that text with escaped quotes. We must
    json.loads the envelope (which un-escapes the inner text) before scanning for
    the {"action":…} block. Handles stream-json (multi-line) too.
    """
    s = (text or "").strip()
    if not s.startswith("{"):
        return text

    def _content_of(obj):
        if not isinstance(obj, dict):
            return None
        if "action" in obj:
            return json.dumps(obj)  # already the outcome itself
        for key in ("result", "content", "text", "message", "response", "output"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v
        return None

    # Single JSON envelope
    try:
        got = _content_of(json.loads(s))
        if got is not None:
            return got
    except json.JSONDecodeError:
        pass
    # stream-json: scan lines bottom-up for the last decodable envelope with content
    for line in reversed(s.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            got = _content_of(json.loads(line))
        except json.JSONDecodeError:
            continue
        if got is not None:
            return got
    return text


def parse_agent_outcome(output) -> dict | None:
    """Extract the structured outcome JSON from an agent's free-form output.

    Returns the parsed dict (with at least an "action" key) or None if no
    structured outcome could be found.
    """
    if isinstance(output, dict):
        return output if "action" in output else None
    if not output:
        return None
    text = _unwrap_provider_output(str(output))

    candidates: list[str] = []
    # 1. fenced ```json ... ``` blocks
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(m.group(1))
    # 2. raw JSON objects scanned with the decoder (handles nesting)
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                candidates.append(json.dumps(obj))
            idx = start + max(end, 1)
        except json.JSONDecodeError:
            idx = start + 1

    # Prefer the last candidate that carries an "action" key
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and "action" in obj:
            return obj
    return None


_OUTCOME_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["work", "skip", "blocked"]},
        "ticket_id": {"type": ["string", "null"]},
        "result": {"type": "string"},
        "new_status": {"type": ["string", "null"]},
        "blocked_reason": {"type": "string"},
        "needs": {"type": "string"},
        "publish_intent": {"type": ["boolean", "null"]},
        "publish_target": {"type": ["string", "null"]},
        "publish_content": {"type": ["string", "null"]},
        "publish_media": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
        # ISO-8601 UTC instant. Present => Postiz schedules the post for that
        # moment instead of publishing immediately (Postiz is the official
        # scheduling intermediary). Absent/null => publish now, as before.
        "publish_at": {"type": ["string", "null"]},
        # Comentários encadeados no próprio post, na ordem. É o que sustenta o
        # "link no primeiro comentário" do LinkedIn: sem isto o texto promete um
        # comentário que nunca existe. Não entra em `required` porque o modelo
        # não precisa emitir — quem preenche é o bridge, que sabe o link.
        "publish_comments": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
    },
    # publish_intent is required (not just present-with-default) so the
    # strict json_schema call is forced to emit it explicitly — the publish
    # gate below is fail-closed and only trusts an EXPLICIT False (Vault V5).
    "required": [
        "action", "result", "publish_intent", "publish_target",
        "publish_content", "publish_media",
    ],
}

# goal-ticket-unification Step 7 (ADR SPEC 3g) — agents that can cause a
# ticket to represent a public post/message. Mirrors STATE_MONITOR_AGENTS
# (heartbeat_runner.py) as a constant + env override pattern.
PUBLISHING_AGENTS = set(
    (os.environ.get("PUBLISHING_AGENTS") or "pixel-social-media,mako-marketing,pulse-community").split(",")
)
# Closed set (Vault V9) — never build a URL/call from an arbitrary agent-supplied string.
# "blog" é o primeiro estágio do fluxo de conteúdo: aprovar o artigo no Ghost
# antes de qualquer coisa derivar dele. Não vai pelo Postiz — vai pelo Ghost
# Admin API (ghost_publisher) — mas usa o MESMO gate, porque a pergunta feita ao
# humano é idêntica: "isto pode ir ao ar?".
PUBLISH_CHANNELS = set(
    (os.environ.get("PUBLISH_CHANNELS")
     or "blog,instagram,linkedin,x,threads,youtube,discord,whatsapp").split(",")
)

# Self-healing review loop (goal-ticket-unification Step 6, ADR SPEC 2b-2d).
# A ticket whose executor sets new_status="review" gets a pass/fail verdict
# before it's allowed to reach resolved — either from raven/oath running
# in-session (anthropic provider, embedded by heartbeat_runner's prompt
# addendum) or, the default path, from verdict_via_nvidia below after the
# provider_fallback lock has already been released. Never a 2nd
# invoke_with_fallback (mutex is re-entrant-unsafe).
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "critique": {"type": "string"},
        "blocking_issues": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["verdict", "critique"],
}

# Max fail-bounces (review -> in_progress -> review) before a ticket parks in
# blocked/review_exhausted for a human. Scoped since the last manual reopen
# (ticket_activity action='review_reset') so a ticket a human fixes and
# reopens doesn't inherit its old bounce count (Raven-F4a).
MAX_REVIEW_BOUNCES = 2


def parse_verdict(output) -> dict | None:
    """Extract a structured review verdict from free-form output.

    Mirrors parse_agent_outcome's candidate-scanning machine but keys on
    "verdict" instead of "action" — an in-session anthropic run may emit BOTH
    the outcome JSON and the verdict JSON in the same final message.
    """
    if isinstance(output, dict):
        return output if "verdict" in output else None
    if not output:
        return None
    text = _unwrap_provider_output(str(output))

    candidates: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(m.group(1))
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                candidates.append(json.dumps(obj))
            idx = start + max(end, 1)
        except json.JSONDecodeError:
            idx = start + 1

    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            return obj
    return None


# Large models that reliably honor response_format=json_schema with good content.
# A short chain so a 429 on one rotates to the next (NVIDIA is free; the limit is
# rate, not cost — see the model-chain rationale).
_STRUCTURER_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "qwen/qwen3.5-397b-a17b",
    "qwen/qwen3.5-122b-a10b",
]


def _nvidia_key_and_base() -> tuple[str, str]:
    import os
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    base = "https://integrate.api.nvidia.com/v1"
    if not key:
        # last resort: read NVIDIA_API_KEY from .env at repo root
        try:
            from pathlib import Path
            env = Path(__file__).resolve().parents[2] / ".env"
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("NVIDIA_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
        except Exception:  # noqa: BLE001
            pass
    return key, base


def structure_via_nvidia(agent_output, agent: str, conn) -> dict | None:
    """Structure the agent's report into outcome JSON using NVIDIA (free).

    The executor models run via the agentic CLI and rarely emit clean JSON. This
    makes a single, cheap completion call with response_format=json_schema (strict)
    on a large model, which guarantees structurally-valid JSON. Free — keeps the
    whole loop on NVIDIA. Falls through to Claude only if every NVIDIA model fails.
    """
    import json as _json
    import urllib.request
    import urllib.error

    report = _unwrap_provider_output(str(agent_output or "")).strip()
    if not report:
        return None
    key, base = _nvidia_key_and_base()
    if not key:
        return None

    rows = conn.execute(
        "SELECT id, title FROM tickets WHERE assignee_agent = ? "
        "AND status IN ('open','in_progress') ORDER BY priority_rank DESC LIMIT 10",
        (agent,),
    ).fetchall()
    tickets = [{"id": (r["id"]),
                "title": (r["title"])} for r in rows]

    prompt = (
        "Converta o relatório de um agente em um JSON de outcome.\n"
        f"Tickets atribuídos ao agente: {_json.dumps(tickets, ensure_ascii=False)}\n\n"
        f"Relatório do agente:\n{report[:4000]}\n\n"
        "Regras:\n"
        "- action='work' se o agente ENTREGOU ou avançou algo concreto (existe um "
        "resultado). Defina new_status: 'resolved' se concluiu, 'review' se precisa "
        "revisão, 'in_progress' se avançou parcialmente.\n"
        "- action='blocked' se depende de algo que só o humano fornece (credencial, "
        "acesso, dado, decisão). Preencha blocked_reason e needs.\n"
        "- action='skip' SOMENTE se nada acionável foi feito.\n"
        "- result: 1 frase em pt-BR com o resultado concreto. ticket_id: o id tratado.\n"
        "- publish_intent: true se o resultado é algo que seria publicado externamente "
        "(post, mensagem, conteúdo pronto pra sair); false se o agente decidiu "
        "explicitamente NÃO publicar agora (rascunho, aguardando revisão); null se a "
        "tarefa não envolve publicação alguma.\n"
        "- publish_target: plataforma de destino. publish_content: texto EXATO que deve "
        "ser publicado (não um resumo). publish_media: URLs HTTPS das mídias, ou null.\n"
        "- publish_at: instante ISO-8601 UTC em que o post deve sair, se o agente "
        "definiu data/hora de agendamento (o Postiz agenda); null para publicar "
        "imediatamente após a aprovação humana."
    )
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 600,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "outcome", "schema": _OUTCOME_SCHEMA,
                                            "strict": True}},
    }
    for model in _STRUCTURER_MODELS:
        body["model"] = model
        try:
            req = urllib.request.Request(
                base + "/chat/completions",
                data=_json.dumps(body).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if content:
                parsed = _json.loads(content)
                if isinstance(parsed, dict) and "action" in parsed:
                    return parsed
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue  # rate-limited → next model
            continue
        except Exception:  # noqa: BLE001
            continue
    return None


def verdict_via_nvidia(work_report, conn) -> dict | None:
    """Get a pass/fail review verdict on a work report via NVIDIA (free), HTTP.

    Default path for the self-healing review loop (ADR SPEC 2c): a plain,
    read-only completion call with response_format=json_schema (strict) on
    _VERDICT_SCHEMA — no filesystem, no subagents, no mutex. Called AFTER the
    provider_fallback lock from the executor's run has already been released,
    so this never nests inside invoke_with_fallback (C1).
    """
    import json as _json
    import urllib.request
    import urllib.error

    report = _unwrap_provider_output(str(work_report or "")).strip()
    if not report:
        return None
    key, base = _nvidia_key_and_base()
    if not key:
        return None

    prompt = (
        "Você é um revisor cético e rigoroso. Avalie o relatório de trabalho abaixo "
        "e decida se o trabalho está pronto para ser considerado concluído (pass) ou "
        "precisa de correção (fail).\n\n"
        f"Relatório do agente:\n{report[:4000]}\n\n"
        "Regras:\n"
        "- verdict='pass' apenas se o relatório descreve um resultado concreto, "
        "verificado (build/teste passou, evidência real), sem pendências bloqueantes.\n"
        "- verdict='fail' se falta evidência, se o próprio relatório admite algo "
        "incompleto/quebrado, ou se a alegação de conclusão não é sustentada.\n"
        "- IMPORTANTE: se o relatório diz que o conteúdo está pronto e aguardando "
        "APROVAÇÃO HUMANA para publicar, isso é verdict='pass'. Publicar não é "
        "trabalho do agente — o gate humano é obrigatório por design, e exigir a "
        "publicação como prova de conclusão cria um impasse: o agente nunca "
        "chega ao gate porque você o reprova por não ter passado por ele.\n"
        "- critique: 1-3 frases em pt-BR explicando a decisão.\n"
        "- blocking_issues: lista curta dos problemas que bloqueiam pass (vazio se pass)."
    )
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "verdict", "schema": _VERDICT_SCHEMA,
                                            "strict": True}},
    }
    for model in _STRUCTURER_MODELS:
        body["model"] = model
        try:
            req = urllib.request.Request(
                base + "/chat/completions",
                data=_json.dumps(body).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if content:
                parsed = _json.loads(content)
                if isinstance(parsed, dict) and "verdict" in parsed:
                    return parsed
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue  # rate-limited → next model
            continue
        except Exception:  # noqa: BLE001
            continue
    return None


def structure_via_claude(agent_output, agent: str, conn) -> dict | None:
    """Hybrid fallback: NVIDIA executes (free, heavy), Claude structures (cheap).

    The NVIDIA models do the actual work but often fail to emit the outcome JSON
    reliably (they narrate, hit max turns, or answer generically). When the raw
    parse fails, we ask the native `claude` CLI (Anthropic subscription) to turn
    the agent's report into the outcome JSON — one turn, no tools, ~hundreds of
    tokens, so it barely touches the Anthropic quota. Returns the outcome dict or
    None if Claude is unavailable / also fails.
    """
    import os
    import shutil
    import subprocess

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return None

    report = _unwrap_provider_output(str(agent_output or "")).strip()
    if not report:
        return None

    # Inbox the agent could have acted on (id + title), so Claude can pick ticket_id
    rows = conn.execute(
        "SELECT id, title FROM tickets WHERE assignee_agent = ? "
        "AND status IN ('open','in_progress') ORDER BY priority_rank DESC LIMIT 10",
        (agent,),
    ).fetchall()
    tickets = []
    for r in rows:
        try:
            tickets.append({"id": r["id"], "title": r["title"]})
        except (TypeError, KeyError, IndexError):
            tickets.append({"id": r[0], "title": r[1]})

    prompt = (
        "Você converte o relatório de um agente em um único JSON de outcome. "
        "Tickets atribuídos ao agente (escolha o ticket_id correto):\n"
        f"{json.dumps(tickets, ensure_ascii=False)}\n\n"
        f"Relatório do agente:\n{report[:4000]}\n\n"
        "Responda SOMENTE com este JSON (uma linha, nada antes/depois):\n"
        '{"action":"work"|"skip"|"blocked","ticket_id":"<id ou null>",'
        '"result":"<o que o agente concluiu, 1 frase pt-BR>",'
        '"new_status":"in_progress"|"review"|"resolved"|null,'
        '"blocked_reason":"<se blocked>","needs":"<se blocked, o que precisa do humano>",'
        '"publish_intent":true|false|null,'
        '"publish_target":"instagram"|"linkedin"|"x"|"threads"|"youtube"|null,'
        '"publish_content":"<texto exato ou null>","publish_media":["<URL HTTPS>"]|null,'
        '"publish_at":"<ISO-8601 UTC do agendamento ou null>"}\n'
        "Regras: action=work se o agente entregou/avançou algo; blocked se ele "
        "depende de dado/credencial/decisão humana; skip se nada foi feito. "
        "Se houver publicação, publish_content deve ser o texto final completo, "
        "não o resumo de result."
    )

    # Clean env so the `claude` CLI uses the Anthropic subscription, not the
    # NVIDIA/OpenAI override vars that may be set for the rest of the workspace.
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("OPENAI_") or k.startswith("CLAUDE_CODE_USE_")
                   or k in ("ANTHROPIC_BASE_URL", "NVIDIA_API_KEY"))}
    try:
        proc = subprocess.run(
            [claude_bin, "--print", "--output-format", "json",
             "--max-turns", "1", "--tools", "", "--", prompt],
            capture_output=True, text=True, timeout=90, env=env,
        )
    except (subprocess.TimeoutExpired, Exception):  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    return parse_agent_outcome(proc.stdout)


def _ticket_title(ticket_id: str, conn) -> str:
    row = conn.execute("SELECT title FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not row:
        return ticket_id
    try:
        return row["title"] or ticket_id
    except (TypeError, KeyError, IndexError):
        return (row[0] if row[0] else ticket_id)


def _recompute_goal_from_tickets(goal_id, conn) -> None:
    """Single source of truth for goals.current_value: COUNT of terminal tickets.

    Idempotent recompute (not an increment) so it stays correct no matter how
    many times it runs for the same goal — reopen/re-resolve, mixed
    goal_id-only/goal_id+task_id populations, all converge to the same number.
    goal_tasks is frozen legacy: this function is the only writer of
    current_value left after goal-ticket-unification (was previously
    triple/quadruple-written by _advance_goal_for_ticket,
    _sync_goal_task_from_ticket, trg_task_done_updates_goal, and the
    current_value field on PATCH /api/goals/{id}).
    """
    if not goal_id:
        return
    goal_row = conn.execute("SELECT metric_type FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if not goal_row:
        return
    metric_type = goal_row["metric_type"]
    # `tasks` conta exatamente a mesma coisa que `count` — tarefas concluídas,
    # que hoje são tickets. Ele ficou de fora deste guard e, como goal_tasks
    # foi congelado no goal-ticket-unification, NADA passou a escrever nessas
    # metas: elas congelaram no valor de junho.
    #
    # O estrago é silencioso e foi o que o Felipe descreveu como "meta que não
    # foi cumprida marcada como cumprida". Medido em 2026-07-26: a meta
    # `pipeline-reels-vertical-pronto` estava `achieved` com current_value=7 e
    # ZERO tickets — o pipeline de vídeo nem existe. `reports-whatsapp`
    # marcava 5/5 com 4 tickets reais, e `evonexus-self-heal` subestimava
    # trabalho já feito (2 gravado contra 3 reais).
    #
    # currency/percentage/boolean seguem de fora com razão: contar tickets ali
    # destruiria o valor real (R$ 45.000 de MRR viraria 1 na primeira
    # transição de status).
    if metric_type not in ("count", "tasks"):
        return
    done = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE goal_id = ? AND status IN ('resolved','closed')",
        (goal_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE goals SET current_value = ?, updated_at = ? WHERE id = ?",
        (float(done), _now_iso(), goal_id),
    )
    conn.execute(
        "UPDATE goals SET status = 'achieved', completed_at = ? "
        "WHERE id = ? AND current_value >= target_value AND status = 'active'",
        (_now_iso(), goal_id),
    )
    conn.execute(
        "UPDATE goals SET status = 'active', completed_at = NULL "
        "WHERE id = ? AND current_value < target_value AND status = 'achieved'",
        (goal_id,),
    )

    # Project rollup (ai-hierarchy-suggestions quick-spec): this is the
    # common real-world path a Goal reaches 'achieved' (ticket resolution),
    # so this is where the Mission->Project->Goal chain's terminal state
    # needs to bubble up, not just the ORM-side routes/goals.py::patch_goal.
    row = conn.execute("SELECT project_id, status FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if row:
        project_id = row["project_id"]
        goal_status = row["status"]
        if goal_status == "achieved" and project_id:
            _maybe_complete_project_raw(project_id, conn)


def _maybe_complete_project_raw(project_id, conn) -> None:
    """Raw-SQL twin of routes/goals.py::_maybe_complete_project.

    This module only ever has a raw sqlite3 connection (no Flask app/request
    context to reach the ORM from), so the rollup check is duplicated here
    rather than shared — same reasoning _recompute_goal_from_tickets itself
    already follows for this whole module.
    """
    proj = conn.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        return
    proj_status = proj["status"]
    if proj_status == "completed":
        return
    rows = conn.execute("SELECT status FROM goals WHERE project_id = ?", (project_id,)).fetchall()
    if not rows:
        return
    statuses = [r["status"] for r in rows]
    if all(s in ("achieved", "cancelled") for s in statuses):
        now = _now_iso()
        conn.execute(
            "UPDATE projects SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, project_id),
        )


def _move_ticket(ticket_id: str, new_status: str, agent: str, comment: str, conn) -> None:
    """Update ticket status + log a comment and an activity event."""
    now = _now_iso()
    prev = conn.execute("SELECT goal_id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    goal_id = (prev["goal_id"] if prev else None)
    resolved_at = now if new_status in ("resolved", "closed") else None
    conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ?, "
        "resolved_at = COALESCE(?, resolved_at) WHERE id = ?",
        (new_status, now, resolved_at, ticket_id),
    )
    _recompute_goal_from_tickets(goal_id, conn)
    if comment:
        import uuid
        conn.execute(
            "INSERT INTO ticket_comments (id, ticket_id, author, body, mentions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), ticket_id, f"agent:{agent}", comment, "[]", now),
        )
        conn.execute(
            "INSERT INTO ticket_activity (id, ticket_id, actor, action, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), ticket_id, f"agent:{agent}", "status_changed",
             json.dumps({"new_status": new_status}), now),
        )
    conn.commit()


def _publish_context_line(ticket_id: str, conn) -> str:
    """Mission/Project context line so an approval doesn't get lost among
    several Sistema Britto projects being worked in parallel — the ticket
    only carries goal_id, so walk goal -> project -> mission."""
    try:
        row = conn.execute(
            "SELECT p.title AS project_title, m.title AS mission_title "
            "FROM tickets t "
            "LEFT JOIN goals g ON g.id = t.goal_id "
            "LEFT JOIN projects p ON p.id = g.project_id "
            "LEFT JOIN missions m ON m.id = p.mission_id "
            "WHERE t.id = ?",
            (ticket_id,),
        ).fetchone()
    except Exception:
        return ""
    if not row:
        return ""
    project_title = row["project_title"]
    mission_title = row["mission_title"]
    if not project_title and not mission_title:
        return ""
    return f"Missão: {mission_title or '—'} · Projeto: {project_title or '—'}"


def _build_publish_approval_body(target: str, outcome: dict, context_line: str = "") -> str:
    """Build the Telegram approval body from what will ACTUALLY be published.

    Trust-critical fix: this used to show outcome["result"] — the agent's
    free-text summary — while _run_publish_action later publishes
    outcome["publish_content"]/publish_media, a DIFFERENT pair of fields.
    A human approving the summary never saw the exact text/media going live.
    Show the real publish_content/publish_media here so "aprovar" means
    "aprovei exatamente isto", not "aprovei um resumo disso".
    """
    content = (outcome.get("publish_content") or "").strip()
    media_urls = outcome.get("publish_media") or []
    if not isinstance(media_urls, list):
        media_urls = []

    lines = [context_line] if context_line else []
    lines.append(f"Plataforma: {target}")

    # When it goes out is as trust-critical as what goes out — approving must
    # never mean "and it may fire at some time I never saw".
    scheduled_at, schedule_error = _parse_publish_at(outcome.get("publish_at"))
    if schedule_error:
        lines.append(f"⚠️ Agendamento inválido: {schedule_error}")
    elif scheduled_at is not None:
        local = scheduled_at.astimezone(_PUBLISH_DISPLAY_ZONE)
        lines.append(f"Agendamento: {local.strftime('%d/%m/%Y %H:%M')} ({PUBLISH_DISPLAY_TZ}) — via Postiz")
    else:
        lines.append("Agendamento: publicação imediata ao aprovar")

    if content:
        lines.append("")
        lines.append("Texto que será publicado:")
        lines.append(content[:800])
    else:
        # Should never reach here in practice — _run_publish_action fails
        # closed on empty publish_content — but never show a blank approval.
        lines.append("")
        lines.append("⚠️ publish_content vazio — a publicação será recusada até isso ser preenchido.")
    if media_urls:
        lines.append("")
        lines.append("Mídia:")
        lines.extend(f"🖼 {u}" for u in media_urls[:5])

    return "\n".join(lines)[:1500]


def _maybe_park_for_publish(ticket_id: str, agent: str, outcome: dict, title: str, conn) -> dict | None:
    """Gate a publishing agent's resolve/close behind human Telegram approval.

    Fail-closed (Vault V5/V9, ADR SPEC 3g): only an EXPLICIT publish_intent=False
    bypasses the gate — absent/None (e.g. the free-form parse_agent_outcome path,
    where the field may simply be missing) still gates. Returns None when there's
    nothing to gate (not a publishing agent, or intent explicitly False); a
    "blocked"/"result" notification spec otherwise (see apply_outcome's contract).
    """
    if agent not in PUBLISHING_AGENTS:
        return None
    if outcome.get("publish_intent") is False:
        return None

    target = outcome.get("publish_target")
    if target not in PUBLISH_CHANNELS:
        reason = f"publish_target inválido: {target!r}"
        conn.execute("UPDATE tickets SET blocked_reason = 'agent_blocked' WHERE id = ?", (ticket_id,))
        _move_ticket(ticket_id, "blocked", agent, reason, conn)
        return {
            "kind": "blocked", "agent": agent, "ticket_id": ticket_id, "ticket_title": title,
            "reason": reason, "needs": "Revisar manualmente.",
        }

    # Idempotency key scoped by attempt (Vault V7) — a prior rejected/expired
    # row for this ticket must not collide with this fresh park.
    attempt = conn.execute(
        "SELECT COUNT(*) FROM pending_approvals WHERE ticket_id = ? AND gate_type = 'publish'",
        (ticket_id,),
    ).fetchone()[0]
    idempotency_key = f"publish:{ticket_id}:{attempt}"
    now = _now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {
        "title": f"Aprovar publicação: {title}",
        "body": _build_publish_approval_body(target, outcome, _publish_context_line(ticket_id, conn)),
        "outcome": outcome,
    }
    conn.execute(
        "INSERT OR IGNORE INTO pending_approvals "
        "(gate_type, ticket_id, agent, attempt, idempotency_key, status, payload, created_at, expires_at) "
        "VALUES ('publish', ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (ticket_id, agent, attempt, idempotency_key, json.dumps(payload, ensure_ascii=False), now, expires_at),
    )
    conn.commit()
    approval_row = conn.execute(
        "SELECT id FROM pending_approvals WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    approval_id = approval_row["id"]

    conn.execute(
        "UPDATE tickets SET blocked_reason = 'pending_human_approval', requires_human_approval = 1 WHERE id = ?",
        (ticket_id,),
    )
    _move_ticket(ticket_id, "blocked", agent, "Aguardando aprovação humana para publicar.", conn)

    from notifications import send_approval_request
    message_id = send_approval_request(approval_id, payload["title"], payload["body"])
    if message_id is not None:
        conn.execute(
            "UPDATE pending_approvals SET telegram_message_id = ? WHERE id = ?",
            (message_id, approval_id),
        )
        conn.commit()

    return {
        "kind": "result", "agent": agent, "ticket_title": title,
        "new_status": "blocked", "summary": "Aguardando aprovação humana para publicar (Telegram).",
    }


def _parse_publish_at(raw) -> tuple[datetime | None, str | None]:
    """Parse an agent-supplied publish_at into an aware UTC datetime.

    Returns (dt, None) on success, (None, None) when there is simply no
    scheduling requested, and (None, reason) when the value is present but
    unusable — the caller fails closed on a reason rather than silently
    downgrading a scheduled post into an immediate publish (which would push
    content out at the wrong time, the exact failure this gate exists to
    prevent).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if not isinstance(raw, str):
        return None, f"publish_at deve ser uma string ISO-8601, recebido {type(raw).__name__}."
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, f"publish_at não é uma data ISO-8601 válida: {raw!r}."
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if parsed <= now:
        return None, f"publish_at está no passado ({parsed.isoformat()}); recuse em vez de publicar imediatamente."
    if parsed > now + timedelta(days=365):
        return None, f"publish_at está a mais de 365 dias ({parsed.isoformat()})."
    return parsed, None


def _publish_settings_for(target: str, content: str, provider: str | None = None) -> dict:
    """Per-platform Postiz settings for the ticket-publish gate.

    `provider` é o `identifier` da integração que o Postiz devolveu, que pode
    ser uma variante do canal lógico (`instagram-standalone` para `instagram`,
    `linkedin-page` para `linkedin`). O `__type` do settings precisa casar com
    o provider REAL da integração, senão o Postiz recusa o payload. Sem o
    parâmetro, cai no próprio target — o comportamento histórico.

    Platforms with a confirmed provider schema go through their real builder
    in postiz_client (X in particular REQUIRES who_can_reply_post — the old
    generic shape was silently rejected by Postiz). Everything else keeps the
    historical generic {"__type": target} shape, which is what the legacy flow
    has always sent for discord/whatsapp.

    Deliberately explicit rather than "any platform present in
    PLATFORM_SETTINGS_BUILDERS": youtube's builder needs a title and tiktok's
    defaults to SELF_ONLY (private), so blindly calling every registered
    builder here would either raise or publish invisibly.
    """
    from postiz_client import (
        build_instagram_payload, build_linkedin_payload, build_threads_payload,
        build_x_payload, build_youtube_payload,
    )

    provider = provider or target
    if target == "instagram":
        return build_instagram_payload(
            post_type="post", standalone=provider == "instagram-standalone",
        )
    if target == "linkedin":
        return build_linkedin_payload(page=provider == "linkedin-page")
    if target == "x":
        return build_x_payload(who_can_reply_post="everyone")
    if target == "threads":
        return build_threads_payload()
    if target == "youtube":
        # The builder requires a 2-100 char title; the ticket flow only carries
        # free text, so derive it from the first line and clamp to the schema.
        first_line = (content.strip().splitlines() or [""])[0].strip()
        title = (first_line or "Sistema Britto")[:100]
        if len(title) < 2:
            title = "Sistema Britto"
        return build_youtube_payload(title=title)
    return {"__type": provider}


def _run_blog_publish(outcome: dict) -> dict:
    """Efetiva a aprovação do artigo: publica ou agenda no Ghost.

    Primeiro estágio do fluxo de conteúdo. Ao publicar, o Ghost dispara o
    webhook post.published, que aciona a ponte para as redes — cada uma com seu
    próprio gate. É por isso que o artigo é aprovado ANTES: post de rede nunca
    nasce de artigo que o humano não liberou.
    """
    ref = (outcome.get("publish_ref") or "").strip()
    if not ref:
        return {"published": False,
                "detail": "publish_ref ausente: sem o id do post no Ghost não há o que publicar."}

    quando, erro = _parse_publish_at(outcome.get("publish_at"))
    if erro:
        return {"published": False, "detail": erro}

    from ghost_publisher import publicar

    resultado = publicar(ref, quando.isoformat() if quando else None)

    # Publicou: derive as redes AQUI, sem esperar o webhook do Ghost.
    #
    # O webhook post.published continua funcionando se existir, mas depender
    # dele é frágil: criar webhook no Ghost exige sessão de staff (chave de API
    # devolve 403/404), ou seja, é um passo manual no painel que nenhum deploy
    # de cliente vai lembrar de fazer. O sintoma seria o pior possível — aprovar
    # o artigo e as redes simplesmente não acontecerem, sem erro nenhum.
    #
    # A ponte é idempotente (`redes_ja_derivadas` checa aprovação já aberta para
    # o artigo antes de gerar), então derivar aqui, o webhook disparar e o
    # varredor passar não produzem aprovação duplicada.
    #
    # Agendado NÃO deriva aqui, e não pode: `distribuir` recusa post que ainda
    # não está `published`, e o Ghost só publica na hora marcada. Quem cobre o
    # agendado é a rotina `derivar_redes_pendentes.py`, a cada 15 minutos — sem
    # ela o artigo agendado nunca chegava às redes, que foi o que aconteceu em
    # 27/07/2026 com os dois artigos do dia.
    if resultado.get("published") and resultado.get("status") != "scheduled":
        _derivar_redes_em_background(ref)
    return resultado


def _derivar_redes_em_background(post_id: str) -> None:
    """Gera as versões de X/LinkedIn/Threads numa thread.

    Em thread porque são três chamadas de geração de texto, cada uma na casa do
    minuto — a decisão de aprovar não pode ficar pendurada esperando isso, ainda
    mais vindo do Telegram, que desiste da requisição antes.
    """
    import threading

    def _trabalhar() -> None:
        try:
            from ghost_social_bridge import distribuir

            distribuir(post_id)
        except Exception:  # noqa: BLE001 — thread solta nunca derruba o processo
            logging.getLogger(__name__).exception("derivação das redes falhou")

    threading.Thread(target=_trabalhar, daemon=True, name=f"deriva-{post_id[:8]}").start()


def _run_publish_action(approval_row, conn) -> dict:
    """Execute the actual publish effect for an approved publish-gate approval.

    Security-critical (ADR SPEC 3f — this is the real incident that motivated
    this whole feature: an orchestrator once fabricated "published
    successfully" without actually publishing). NEVER return published=True
    without genuine confirmation from the external platform's API.

    Postiz's POST /public/v1/posts only confirms that a workflow was created.
    We therefore poll GET /public/v1/posts and return published=True only after
    every returned post id reaches state=PUBLISHED. QUEUE/ERROR/timeouts remain
    fail-closed and the ticket is not resolved.

    HTTP transport lives in postiz_client.PostizClient (social-media-production
    feature) — this function is the only caller for the legacy ticket-publish
    flow, kept separate from the MediaJob pipeline's use of the same client.
    """
    from postiz_client import PostizClient, PostizError

    try:
        payload = json.loads(approval_row.payload or "{}")
    except (ValueError, TypeError):
        payload = {}
    outcome = payload.get("outcome") or {}
    target = outcome.get("publish_target")
    content = (outcome.get("publish_content") or "").strip()

    if target not in PUBLISH_CHANNELS:
        return {"published": False, "detail": f"publish_target inválido: {target!r}."}
    if not content:
        return {
            "published": False,
            "detail": "publish_content vazio; o resumo result nunca é publicado como conteúdo.",
        }

    # Segunda barreira do limite de tamanho — a primeira recusa o gate na
    # criação (`routes/approvals._recusar_se_estoura`). Esta existe para os
    # cards que já estavam abertos quando aquela entrou, e porque gastar uma
    # chamada ao Postiz que sabemos que volta 400 só produz ruído no log e um
    # ticket desbloqueado sem motivo claro.
    if target != "blog":
        try:
            from ghost_social_bridge import LIMITES, medida, teto_de

            if target in LIMITES and medida(content) > teto_de(target):
                return {
                    "published": False,
                    "detail": (f"texto de {medida(content)} bytes não cabe em {target} "
                               f"({teto_de(target)} bytes com margem); o Postiz recusaria "
                               f"com 400. Reescreva mais curto."),
                }
        except ImportError:
            pass  # sem a régua, segue e deixa o Postiz decidir

    # Blog sai pelo Ghost, não pelo Postiz. O que se publica aqui é o artigo
    # identificado por publish_ref — nunca o texto do card, que é resumo para o
    # humano ler. Confundir os dois publicaria o resumo como se fosse o artigo.
    if target == "blog":
        return _run_blog_publish(outcome)

    client = PostizClient.from_env()
    if client is None:
        return {
            "published": False,
            "detail": "POSTIZ_URL/POSTIZ_API_KEY não configurados no serviço do dashboard.",
        }

    try:
        integrations = client.list_integrations()
    except PostizError as exc:
        return {"published": False, "detail": f"Falha ao consultar integrações do Postiz: {exc}"}

    integration = client.select_integration(target, integrations)
    if not integration:
        return {
            "published": False,
            "detail": f"Nenhuma integração Postiz ativa e inequívoca para {target!r}.",
        }

    media_urls = outcome.get("publish_media") or []
    if not isinstance(media_urls, list):
        return {"published": False, "detail": "publish_media deve ser uma lista de URLs HTTPS."}
    media = []
    for index, media_url in enumerate(media_urls):
        if not isinstance(media_url, str) or not client.is_safe_media_url(media_url):
            return {"published": False, "detail": f"URL de mídia inválida: {media_url!r}."}
        media.append({"id": f"evonexus-{index}", "path": media_url})

    if target == "instagram" and not media:
        return {
            "published": False,
            "detail": "Instagram requer publish_media com ao menos uma URL HTTPS.",
        }

    settings = _publish_settings_for(target, content, provider=integration.get("identifier"))

    # Comentários encadeados no post (LinkedIn: o link do artigo, que o texto
    # aprovado promete estar "no primeiro comentário"). Validados como texto
    # simples — nunca como URL de mídia, que segue outra allowlist.
    comentarios_brutos = outcome.get("publish_comments") or []
    if not isinstance(comentarios_brutos, list):
        return {"published": False, "detail": "publish_comments deve ser uma lista de textos."}
    comentarios = [c.strip() for c in comentarios_brutos if isinstance(c, str) and c.strip()]

    # Scheduling path — Postiz is the official scheduling intermediary. When the
    # approved outcome carries publish_at, we hand Postiz the date and let it
    # own the timer instead of publishing on the spot.
    scheduled_at, schedule_error = _parse_publish_at(outcome.get("publish_at"))
    if schedule_error:
        return {"published": False, "detail": schedule_error}

    if scheduled_at is not None:
        try:
            created = client.schedule_post(
                integration_id=integration["id"], content=content, media=media, settings=settings,
                scheduled_at_utc=scheduled_at.isoformat(), comments=comentarios,
            )
        except PostizError as exc:
            return {"published": False, "detail": f"Postiz recusou o agendamento: {exc}"}

        post_ids = [item.get("postId") for item in created if isinstance(item, dict) and item.get("postId")]
        if not post_ids:
            return {"published": False, "detail": f"Postiz não retornou postId no agendamento: {created!r}"}

        window = (
            (scheduled_at - timedelta(days=1)).isoformat(),
            (scheduled_at + timedelta(days=1)).isoformat(),
        )
        confirmation = client.confirm_scheduled(post_ids, window=window)
        # The ticket only resolves on a confirmed effect. A scheduled post is a
        # real, confirmed effect (it is queued on Postiz) even though it is not
        # PUBLISHED yet — so map scheduled=True onto published=True for the
        # approval bookkeeping, and say plainly in the detail that it is queued.
        return {
            "published": bool(confirmation.get("scheduled")),
            "scheduled_at": scheduled_at.isoformat(),
            "detail": confirmation.get("detail", ""),
            # Vazio enquanto agendado — a plataforma só devolve o endereço do
            # post depois de publicar. Quem fecha essa lacuna é o confirmador
            # de agendamentos (scripts/confirmar_agendamentos.py).
            "release_urls": confirmation.get("release_urls") or [],
            "post_ids": confirmation.get("post_ids") or post_ids,
            "media_count": len(media),
            "comment_count": len(comentarios),
        }

    try:
        created = client.create_post_now(
            integration_id=integration["id"], content=content, media=media, settings=settings,
            now_iso_utc=_now_iso(), comments=comentarios,
        )
    except PostizError as exc:
        return {"published": False, "detail": f"Postiz recusou a publicação: {exc}"}

    post_ids = [item.get("postId") for item in created if isinstance(item, dict) and item.get("postId")]
    if not post_ids:
        return {"published": False, "detail": f"Postiz não retornou postId: {created!r}"}

    wait_seconds = float(os.environ.get("POSTIZ_PUBLISH_TIMEOUT_SECONDS", "90"))
    poll_seconds = max(float(os.environ.get("POSTIZ_PUBLISH_POLL_SECONDS", "3")), 0.1)
    window = (
        (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    try:
        resultado = client.wait_for_publication(
            post_ids, wait_seconds=wait_seconds, poll_seconds=poll_seconds, window=window
        )
    except PostizError as exc:
        return {"published": False, "detail": f"Falha ao confirmar publicação no Postiz: {exc}"}
    resultado.setdefault("post_ids", post_ids)
    resultado["media_count"] = len(media)
    resultado["comment_count"] = len(comentarios)
    return resultado


def _last_review_reset_at(ticket_id: str, conn) -> str | None:
    """created_at of the most recent 'review_reset' activity for this ticket, if any."""
    row = conn.execute(
        "SELECT created_at FROM ticket_activity WHERE ticket_id = ? AND action = 'review_reset' "
        "ORDER BY created_at DESC LIMIT 1",
        (ticket_id,),
    ).fetchone()
    if not row:
        return None
    return row["created_at"]


def _count_review_bounces(ticket_id: str, conn) -> int:
    """Count of 'review_bounce' activity since the last 'review_reset' (or all-time if none).

    Scoping to the last reset means a manually-reopened ticket (see
    review_reset semantics in .claude/rules/tickets.md and routes/tickets.py)
    starts its bounce budget over, instead of inheriting a stale count from a
    previous review cycle (Raven-F4a).
    """
    since = _last_review_reset_at(ticket_id, conn)
    if since:
        row = conn.execute(
            "SELECT COUNT(*) FROM ticket_activity WHERE ticket_id = ? AND action = 'review_bounce' "
            "AND created_at > ?",
            (ticket_id, since),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM ticket_activity WHERE ticket_id = ? AND action = 'review_bounce'",
            (ticket_id,),
        ).fetchone()
    return row[0] if row else 0


def _apply_review_verdict(ticket_id: str, agent: str, verdict_obj: dict, conn) -> dict:
    """Route a parsed review verdict: pass -> resolved; fail -> bounce or exhaust.

    Returns {"verdict": "pass"|"fail", "critique": str, "exhausted": bool, "bounce": int}.
    """
    verdict = str(verdict_obj.get("verdict", "")).strip().lower()
    critique = (verdict_obj.get("critique") or "").strip()

    if verdict == "pass":
        _move_ticket(ticket_id, "resolved", agent, critique or "Revisão: aprovado.", conn)
        return {"verdict": "pass", "critique": critique, "exhausted": False, "bounce": 0}

    n = _count_review_bounces(ticket_id, conn)
    if n < MAX_REVIEW_BOUNCES:
        _move_ticket(ticket_id, "in_progress", agent,
                     f"Revisão reprovou: {critique}" if critique else "Revisão reprovou.", conn)
        import uuid
        conn.execute(
            "INSERT INTO ticket_activity (id, ticket_id, actor, action, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), ticket_id, f"agent:{agent}", "review_bounce",
             json.dumps({"critique": critique}), _now_iso()),
        )
        conn.commit()
        return {"verdict": "fail", "critique": critique, "exhausted": False, "bounce": n + 1}

    # Bounces exhausted — own blocked_reason ('review_exhausted'), distinct
    # from 'agent_blocked' (AC8 separates the two semantics, Raven-F4b), plus
    # an explicit human notification (never the generic blocked queue).
    conn.execute("UPDATE tickets SET blocked_reason = 'review_exhausted' WHERE id = ?", (ticket_id,))
    _move_ticket(ticket_id, "blocked", agent,
                 f"Revisão esgotou {MAX_REVIEW_BOUNCES} tentativas." +
                 (f" Última crítica: {critique}" if critique else ""), conn)
    return {"verdict": "fail", "critique": critique, "exhausted": True, "bounce": n}


def apply_outcome(heartbeat_id: str, agent: str, result: dict, conn) -> dict | None:
    """Apply the agent's outcome to the kanban and return a notification spec.

    Returns a dict {kind, ...} describing what (if anything) to notify, or None
    for silence. The caller (heartbeat_runner) turns this into a Telegram message.
    """
    status = result.get("status", "fail")

    # Technical failure of the run itself — surface it compactly, it may be real.
    if status != "success":
        return {
            "kind": "tech_fail",
            "agent": agent,
            "heartbeat_id": heartbeat_id,
            "error": (result.get("error") or "execução falhou")[:300],
        }

    raw_output = result.get("output") or result.get("result") or result.get("handler_result")
    outcome = parse_agent_outcome(raw_output)
    if not outcome:
        # NVIDIA executed but didn't emit clean JSON → structure it. Try NVIDIA
        # first (free, json_schema-forced), then Claude as a last resort.
        outcome = structure_via_nvidia(raw_output, agent, conn)
    if not outcome:
        outcome = structure_via_claude(raw_output, agent, conn)
    if not outcome:
        return None  # nobody could structure it → silent no-op (no spam)

    action = str(outcome.get("action", "")).strip().lower()
    ticket_id = outcome.get("ticket_id") or None
    summary = (outcome.get("result") or "").strip()

    if action == "skip":
        return None

    if action == "blocked":
        reason = (outcome.get("blocked_reason") or summary or "sem detalhes").strip()
        needs = (outcome.get("needs") or "").strip()
        title = _ticket_title(ticket_id, conn) if ticket_id else ""
        if ticket_id:
            _move_ticket(ticket_id, "blocked", agent,
                         f"Bloqueado: {reason}" + (f"\nPrecisa: {needs}" if needs else ""), conn)
        return {
            "kind": "blocked",
            "agent": agent,
            "ticket_id": ticket_id or "",
            "ticket_title": title,
            "reason": reason,
            "needs": needs,
        }

    if action == "work":
        new_status = _normalize_status(outcome.get("new_status")) or "in_progress"
        title = _ticket_title(ticket_id, conn) if ticket_id else ""

        # Self-healing review loop (Step 6): a ticket the executor thinks is
        # done doesn't go straight to resolved — it needs a pass/fail verdict
        # first. Try to parse one already embedded in this same response
        # (in-session anthropic path, heartbeat_runner's prompt addendum);
        # if absent (the nvidia default), fetch one via the read-only HTTP
        # fallback — never a 2nd invoke_with_fallback.
        # Conteúdo público com publish_intent=true vai DIRETO para o gate humano,
        # sem passar pelo revisor automático.
        #
        # Antes, o gate só era alcançável depois de um verdict='pass' (ver abaixo),
        # e o revisor reprovava justamente porque nada tinha sido publicado ainda —
        # um impasse fechado: o agente não chegava ao gate porque era reprovado por
        # não ter passado pelo gate. Em produção isso queimou 6 ciclos do mesmo post
        # até 'review_exhausted' (Telegram, 24-25/07/2026).
        #
        # O gate do Telegram JÁ É a revisão para conteúdo público: um humano lê o
        # texto exato e a data antes de qualquer coisa sair. Rodar um revisor
        # automático antes dele é redundante e, como se viu, ativamente nocivo.
        if (ticket_id and new_status in ("review", "resolved", "closed")
                and agent in PUBLISHING_AGENTS and outcome.get("publish_intent") is True):
            gate = _maybe_park_for_publish(ticket_id, agent, outcome, title, conn)
            if gate is not None:
                return gate

        if ticket_id and new_status == "review":
            _move_ticket(ticket_id, "review", agent, summary or "Trabalho enviado para revisão.", conn)
            verdict = parse_verdict(raw_output) or verdict_via_nvidia(raw_output, conn)
            if not verdict:
                # No reviewer available this run — leave parked in review for
                # a human or the next wake, rather than silently auto-passing.
                return {
                    "kind": "result", "agent": agent, "ticket_title": title,
                    "new_status": "review", "summary": summary or "Aguardando revisão.",
                }
            review = _apply_review_verdict(ticket_id, agent, verdict, conn)
            if review["verdict"] == "pass":
                gate = _maybe_park_for_publish(ticket_id, agent, outcome, title, conn)
                if gate is not None:
                    return gate
                return {
                    "kind": "result", "agent": agent, "ticket_title": title,
                    "new_status": "resolved", "summary": review["critique"] or "Revisão aprovada.",
                }
            if review["exhausted"]:
                return {
                    "kind": "blocked", "agent": agent, "ticket_id": ticket_id, "ticket_title": title,
                    "reason": f"Revisão reprovou {MAX_REVIEW_BOUNCES}x: {review['critique'] or 'sem detalhes'}",
                    "needs": "Revisar o ticket manualmente — bounces de revisão esgotados.",
                }
            return {
                "kind": "result", "agent": agent, "ticket_title": title,
                "new_status": "in_progress",
                "summary": f"Revisão reprovou (bounce {review['bounce']}/{MAX_REVIEW_BOUNCES}): "
                           f"{review['critique'] or 'sem detalhes'}",
            }

        if ticket_id:
            if new_status in ("resolved", "closed"):
                gate = _maybe_park_for_publish(ticket_id, agent, outcome, title, conn)
                if gate is not None:
                    return gate
            _move_ticket(ticket_id, new_status, agent, summary or "Trabalho realizado.", conn)
        if not summary:
            return None  # worked but reported nothing meaningful → stay silent
        return {
            "kind": "result",
            "agent": agent,
            "ticket_title": title,
            "new_status": new_status,
            "summary": summary,
        }

    return None
