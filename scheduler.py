#!/usr/bin/env python3
"""
EvoNexus Scheduler
Runs core routines on schedule. Custom routines loaded from config/routines.yaml.
Usage: runs automatically with make dashboard-app
"""

import subprocess
import os
import sys
import shlex
import signal
import threading
import time
from datetime import date, datetime
from pathlib import Path

WORKSPACE = Path(__file__).parent
PYTHON = "uv run python" if os.system("command -v uv > /dev/null 2>&1") == 0 else "python3"
ROUTINES_DIR = WORKSPACE / "ADWs" / "routines"
PID_FILE = WORKSPACE / "ADWs" / "logs" / "scheduler.pid"

# SIGHUP reload flag — set by handler, cleared by main loop (ADR-2)
_reload_flag = threading.Event()


def _handle_sighup(signum, frame):
    """POSIX: only async-signal-safe ops here. Event.set() qualifies."""
    _reload_flag.set()


def acquire_lock() -> bool:
    """Ensure only one scheduler instance runs. Returns False if another is alive.

    Uses O_CREAT|O_EXCL for atomic creation, then validates the PID inside.
    Avoids the TOCTOU race where two processes both see a stale PID file and
    both proceed to start.
    """
    import fcntl
    # ADWs/logs/ is not in git (no .gitkeep) and setup.py's create_folders
    # only makes the user-facing workspace dirs, so on a fresh clone the
    # parent of PID_FILE doesn't exist and os.open() raises FileNotFoundError
    # before the scheduler can even start. Make it idempotently.
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(PID_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # File exists — check if the owner is still alive
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            os.kill(existing_pid, 0)
            print(f"  Scheduler already running (PID {existing_pid}). Exiting.")
            return False
        except (ProcessLookupError, ValueError):
            # Stale lock — remove and retry once
            PID_FILE.unlink(missing_ok=True)
            try:
                fd = os.open(str(PID_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return True
            except FileExistsError:
                print("  Scheduler lock contention — another instance just started. Exiting.")
                return False


def release_lock():
    """Remove PID file on clean shutdown."""
    PID_FILE.unlink(missing_ok=True)


# ── janela perdida ───────────────────────────────────────────────────────
#
# `schedule` agenda sempre a PRÓXIMA ocorrência a partir do instante em que o
# job é registrado. Um processo que sobe domingo às 12:15 registra o research
# semanal (domingo 08:00) para o domingo SEGUINTE — a semana inteira se perde
# em silêncio, sem erro, sem log.
#
# Aconteceu em 02/08/2026: um redeploy pôs o scheduler de pé às 12:15 e o
# `weekly_content_research` das 08:00 nunca rodou. A segunda-feira amanheceu
# com um ciclo de 11 pautas (montado à mão dias antes) em vez das 21 da semana,
# com três keywords duplicadas, e a esteira ficou sem material novo.
#
# O catch-up é deliberadamente estreito: só job SEMANAL, só se a janela de HOJE
# já passou, e só se ele não rodou hoje. Diário perdido espera algumas horas
# pela próxima janela; semanal perdido espera sete dias.

MARCAS_DIR = WORKSPACE / "ADWs" / "logs" / "ultima-execucao"
DIAS_DA_SEMANA = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                  "friday": 4, "saturday": 5, "sunday": 6}


def _marca(script: str) -> Path:
    return MARCAS_DIR / f"{Path(script).name}.txt"


def _marcar_execucao(script: str) -> None:
    """Registra que a rotina rodou hoje. Só o sucesso conta — uma execução que
    falhou tem de ser retentada pelo catch-up do próximo boot, não considerada
    feita."""
    try:
        MARCAS_DIR.mkdir(parents=True, exist_ok=True)
        _marca(script).write_text(date.today().isoformat(), encoding="utf-8")
    except OSError:
        pass  # marca é otimização de catch-up, nunca requisito da rotina


def _rodou_hoje(script: str) -> bool:
    try:
        return _marca(script).read_text(encoding="utf-8").strip() == date.today().isoformat()
    except OSError:
        return False


def recuperar_janelas_perdidas() -> None:
    """Roda agora o job semanal cuja janela de hoje passou sem ele."""
    import schedule

    agora = datetime.now()
    for job in schedule.get_jobs():
        if job.unit != "weeks" or not job.start_day or not job.at_time:
            continue
        if DIAS_DA_SEMANA.get(str(job.start_day).lower()) != agora.weekday():
            continue
        alvo = agora.replace(hour=job.at_time.hour, minute=job.at_time.minute,
                             second=0, microsecond=0)
        if agora <= alvo:
            continue  # a janela ainda vem; o próprio schedule dá conta
        args = getattr(job.job_func, "args", ()) or ()
        if len(args) < 2:
            continue
        name, script = args[0], args[1]
        if _rodou_hoje(script):
            continue
        print(f"  [catch-up] {name} perdeu a janela das {alvo:%H:%M} — rodando agora",
              flush=True)
        try:
            job.job_func()
        except Exception as exc:  # noqa: BLE001 — catch-up nunca derruba o boot
            print(f"  [catch-up] {name} falhou: {exc}", flush=True)


def _alert_routine_failure(name: str, detail: str) -> None:
    """Avisa que uma rotina falhou, pelo mesmo canal que o resto do sistema usa.

    O stderr da rotina já vai para o log desde 2502025, mas log é passivo:
    alguém precisa ir olhar. Foi assim que `publish_scheduled.py` passou semanas
    falhando a cada tick sem ninguém saber, e assim que a esteira falhou em
    02/08 sem que o motivo aparecesse até rodar na mão.

    Best-effort por definição: se o Telegram não estiver configurado ou o import
    falhar, o print do chamador já aconteceu.
    """
    try:
        sys.path.insert(0, str(WORKSPACE / "dashboard" / "backend"))
        from notifications import _esc, send_telegram_alert

        send_telegram_alert(
            f"⚠️ <b>Rotina falhou</b>\n\n"
            f"🔧 <b>{_esc(name)}</b>\n\n"
            f"📝 <pre>{_esc(detail)}</pre>"
        )
    except Exception as exc:  # noqa: BLE001 — alerta nunca derruba a rotina
        print(f"  (não foi possível alertar sobre {name}: {type(exc).__name__}: {exc})",
              flush=True)


def run_adw(name: str, script: str, args: str = ""):
    """Execute a routine as subprocess.

    YAML-configured routines are always requested with a "custom/" prefix
    (see _load_routines_from_yaml) even when the real script lives elsewhere
    — e.g. daily_status_report.py sits directly in ADWs/routines/ (not
    custom/), and publish_scheduled.py sits at the repo's top-level scripts/.
    Moving either would break their own ROOT-relative path resolution
    (calendar/ledger/DB paths computed from Path(__file__).parent chains), so
    this tries a few candidate locations instead of relocating them:
    1. exactly what the caller asked for (custom/<script>)
    2. ADWs/routines/<basename>, ignoring any custom/ prefix
    3. top-level scripts/<basename>
    """
    now = datetime.now().strftime("%H:%M")
    basename = Path(script).name
    candidates = [ROUTINES_DIR / script, ROUTINES_DIR / basename, WORKSPACE / "scripts" / basename]
    script_path = next((p for p in candidates if p.exists()), None)
    if script_path is None:
        print(f"  {now} ✗ {name} — script not found: {script}", flush=True)
        # Um print aqui foi exatamente o que deixou `publish_scheduled.py` falhar
        # a cada tick por semanas sem ninguém notar (ver .claude/rules/routines.md).
        # A correção da época acrescentou os candidatos de path acima; o modo de
        # falha silenciosa em si continuava intacto até aqui.
        _alert_routine_failure(
            name,
            f"script não encontrado: {script}\nprocurado em:\n  "
            + "\n  ".join(str(p) for p in candidates),
        )
        return

    try:
        # Lista em vez de shell=True: sem interpolação de `args` numa string de
        # shell, e caminho com espaço deixa de ser problema. PYTHON pode ser
        # "uv run python" (várias palavras), daí o shlex.split.
        cmd = shlex.split(PYTHON) + [str(script_path)]
        if args:
            cmd += shlex.split(args)
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE),
            timeout=900,
            capture_output=True,
            text=True,
        )
        status = "✓" if result.returncode == 0 else "✗"
        print(f"  {now} {status} {name}", flush=True)
        if result.returncode == 0:
            _marcar_execucao(script)
        # O erro da rotina não pode sumir. Sem isto, uma esteira que falha às
        # 06:00 loga só "✗ Esteira de Conteúdo" e ninguém descobre por quê —
        # foi exatamente o que aconteceu em 02/08 (a rotina falhou e o motivo
        # ficou invisível até rodar na mão). O erro vai para o stderr do
        # scheduler, que o Swarm agrega e o Growth Pulse enxerga.
        if result.returncode != 0 and (result.stderr or result.stdout):
            trecho = (result.stderr or result.stdout).strip()[-2000:]
            for linha in trecho.splitlines()[-6:]:
                print(f"    └ {name}: {linha[:400]}", flush=True)
        if result.returncode != 0:
            saida = (result.stderr or result.stdout or "").strip()
            _alert_routine_failure(
                name, f"exit {result.returncode}\n\n{(saida or '(sem saída)')[-800:]}")
    except subprocess.TimeoutExpired as exc:
        print(f"  {now} ✗ {name} timeout (15min)", flush=True)
        _alert_routine_failure(name, "timeout após 15 minutos")
        saida = (exc.stdout or "") + (exc.stderr or "")
        if saida:
            trecho = saida.strip()[-2000:]
            for linha in trecho.splitlines()[-6:]:
                print(f"    └ {name}: {linha[:400]}", flush=True)
    except Exception as e:
        print(f"  {now} ✗ {name} error: {e}", flush=True)


def setup_schedule():
    """Configure core routines. Custom routines loaded from config/routines.yaml."""
    import schedule

    # ── Core routines (shipped with repo) ──
    schedule.every().day.at("07:00").do(run_adw, "Good Morning", "good_morning.py")
    schedule.every().day.at("21:00").do(run_adw, "End of Day", "end_of_day.py")
    schedule.every().day.at("21:15").do(run_adw, "Memory Sync", "memory_sync.py")
    # Reativado (panorama 2026-07-17, item 4) — o comentário anterior dizia
    # "replaced by Weekly Review (Team) in routines.yaml", mas essa entrada
    # nunca existiu em config/routines.yaml; nada mais checa Goal/Ticket
    # vencido sem isto.
    schedule.every().friday.at("08:00").do(run_adw, "Weekly Review", "weekly_review.py")
    schedule.every().sunday.at("09:00").do(run_adw, "Memory Lint", "memory_lint.py")
    schedule.every().day.at("21:00").do(run_adw, "Daily Backup", "backup.py")
    # 20:00, uma hora antes do backup: avisa se o artefato mais recente (local
    # ou S3) está com mais de 48h — o backup "✓" silencioso enganou por dias
    # entre 24/07 e 28/07, e este watchdog é o que torna a falha audível.
    schedule.every().day.at("20:00").do(run_adw, "Backup Watchdog", "backup_watchdog.py")
    # REMOVIDO: "Uso Modelos DIA" (uso_modelos_dia.py) — fazia 12 chamadas/dia
    # a modelos NVIDIA só para pingar com prompt artificial, sem produzir
    # lead, conteúdo ou decisão. Custo e quota desperdiçados. A Saúde dos
    # modelos agora é observada por falha real (provider_fallback já loga
    # 429/timeout por tarefa) e reportada pelo Growth Pulse, não por sondagem
    # cega.

    # ── Esteira de conteúdo ──
    #
    # Domingo levanta as 21 pautas da semana (3/dia, segunda a domingo)
    # cruzando notícia da semana com volume de busca real; nada é publicado,
    # abre um ticket para o humano aprovar o ciclo em lote.
    #
    # Todo dia às 06:00 a esteira consome as pautas aprovadas daquele dia:
    # escreve o artigo com o humanizer, cria o rascunho no Ghost, gera a capa
    # e para no gate. 06:00 dá folga confortável até o primeiro slot de
    # publicação (09:00 BRT) para o humano aprovar sem correr.
    schedule.every().sunday.at("08:00").do(
        run_adw, "Research Semanal de Pauta", "weekly_content_research.py")
    # 07:45, antes do research: cruza cliques por artigo + visitas de funil com
    # a fila de pautas e deixa auditoria_temas.json pronto para a próxima
    # esteira. É o dado que impede o ciclo seguinte de saturar um nicho.
    schedule.every().sunday.at("07:45").do(
        run_adw, "Auditoria de Temas", "auditoria_temas.py")
    schedule.every().day.at("06:00").do(
        run_adw, "Esteira de Conteúdo", "daily_content_pipeline.py")
    # 05:30, antes da esteira: o número do dia reflete o que o conteúdo de
    # ontem produziu, sem contar a publicação de hoje que ainda nem saiu.
    schedule.every().day.at("05:30").do(
        run_adw, "Métricas de Crescimento", "daily_growth_metrics.py")
    # Fase 4 (Facebook/Meta Ads). Zero campanha ativa em 29/07/2026 — a
    # rotina existe pra já estar medindo no dia em que uma entrar no ar.
    schedule.every().day.at("05:35").do(
        run_adw, "Facebook Ads Pulse", "facebook_ads_pulse.py")

    # A cada 30 minutos: artigo publicado que ainda não virou post de rede.
    #
    # O gate do blog aceita agendamento, e artigo agendado o Ghost publica
    # sozinho, sem passar por código nosso — a derivação das redes só rodava no
    # caminho da publicação imediata. Em 27/07/2026 os dois artigos do dia foram
    # agendados, o Ghost publicou os dois, e nenhum post de X, LinkedIn ou
    # Threads existiu. O varredor é idempotente (checa aprovação já aberta antes
    # de derivar), então passar de 15 em 15 minutos não empilha notificação.
    schedule.every(30).minutes.do(
        run_adw, "Derivar Redes Pendentes", "derivar_redes_pendentes.py")

    # Domingo 09:00, uma hora depois do research: a semana já fechou e as
    # métricas de sábado já foram coletadas. Lê o funil, acha o maior
    # vazamento e abre um ticket com a hipótese — a decisão continua humana,
    # e é ela que vira memória para a revisão seguinte.
    schedule.every().sunday.at("09:00").do(
        run_adw, "Revisão do Funil", "weekly_funnel_review.py")

    # Growth & Presence Pulse — 2x/dia (08:30 e 18:30 BRT).
    # Substitui o hourly_report antigo que mandava 12 msg/dia com baixa
    # densidade e falhava por não ter DB/Telegram no scheduler.
    # Pulse completo de manhã e fim de tarde; alerta crítico a cada 6h.
    schedule.every().day.at("08:30").do(run_adw, "Growth Pulse", "growth_pulse.py")
    schedule.every().day.at("18:30").do(run_adw, "Growth Pulse", "growth_pulse.py")
    schedule.every(6).hours.do(run_adw, "Growth Pulse Alert", "growth_pulse.py", "--alert")

    # ── Custom routines (from config/routines.yaml if exists) ──
    _load_custom_routines(schedule)


def _coerce_interval(interval, time_str):
    """Return an interval in minutes, or None to fall back to a daily .at(time).

    Accepts an explicit `interval` (minutes) or a cron-style `*/N * * * *` time
    field (common mistake / convenience), converting it to N minutes. Anything
    else (HH:MM) returns None so the caller uses the daily-at path.
    """
    if interval is not None:
        return int(interval)
    if isinstance(time_str, str):
        import re
        m = re.match(r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$", time_str.strip())
        if m:
            return int(m.group(1))
    return None


def _load_routines_from_yaml(schedule, config_path: Path, is_plugin: bool = False,
                             disabled_make_ids: set | None = None):
    """Load routines from a single YAML file into the schedule.

    For plugin files, errors are swallowed (broken plugin doesn't kill core).
    For the core config, errors are re-raised.

    Wave 1.1: if disabled_make_ids is provided, skip matching make-ids.
    The make-id for a plugin routine is derived as: plugin-{slug}-{name.lower().replace(' ','-')}.
    """
    import yaml

    if not config_path.exists():
        return

    _disabled = disabled_make_ids or set()

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not config:
            return

        source_label = f"plugin:{config_path.parent.name}" if is_plugin else "core"
        # Determine slug for make-id derivation (only used for plugin routines)
        plugin_slug = config_path.parent.name if is_plugin else ""

        for r in config.get("daily", []) or []:
            if not r.get("enabled", True):
                continue
            script = r.get("script", "")
            name = r.get("name", script)
            args = r.get("args", "")
            # Wave 1.1: check if this routine is individually disabled
            if _disabled and is_plugin:
                make_id = f"plugin-{plugin_slug}-{name.lower().replace(' ', '-')}"
                if make_id in _disabled:
                    print(f"  [{source_label}] skipped disabled routine '{name}' ({make_id})")
                    continue
            try:
                interval_min = _coerce_interval(r.get("interval"), r.get("time"))
                if interval_min is not None:
                    schedule.every(interval_min).minutes.do(run_adw, name, f"custom/{script}", args)
                elif r.get("time"):
                    schedule.every().day.at(r["time"]).do(run_adw, name, f"custom/{script}", args)
            except Exception as exc:
                print(f"  [{source_label}] SKIPPED routine '{name}': invalid schedule "
                      f"(time={r.get('time')!r}, interval={r.get('interval')!r}): {exc}")

        for r in config.get("weekly", []) or []:
            if not r.get("enabled", True):
                continue
            script = r.get("script", "")
            name = r.get("name", script)
            args = r.get("args", "")
            # Wave 1.1: check if this routine is individually disabled
            if _disabled and is_plugin:
                make_id = f"plugin-{plugin_slug}-{name.lower().replace(' ', '-')}"
                if make_id in _disabled:
                    print(f"  [{source_label}] skipped disabled routine '{name}' ({make_id})")
                    continue
            day = r.get("day", "friday").lower()
            time_str = r.get("time", "09:00")
            days = r.get("days", [day])
            try:
                for d in days:
                    getattr(schedule.every(), d, schedule.every().friday).at(time_str).do(
                        run_adw, name, f"custom/{script}", args
                    )
            except Exception as exc:
                print(f"  [{source_label}] SKIPPED weekly routine '{name}': invalid time "
                      f"{time_str!r}: {exc}")
                continue

        global _monthly_routines
        monthly = config.get("monthly", []) or []
        # Wave 1.1: filter disabled monthly routines for plugins
        if _disabled and is_plugin:
            filtered_monthly = []
            for r in monthly:
                name = r.get("name", r.get("script", ""))
                make_id = f"plugin-{plugin_slug}-{name.lower().replace(' ', '-')}"
                if make_id in _disabled:
                    print(f"  [{source_label}] skipped disabled monthly routine '{name}' ({make_id})")
                else:
                    filtered_monthly.append(r)
            monthly = filtered_monthly
        # Plugin monthly routines are appended; core replaces the list
        if is_plugin:
            _monthly_routines.extend(monthly)
        else:
            _monthly_routines = monthly

    except Exception as e:
        # Confirmed live 2026-07-14: a single bad indent in config/routines.yaml
        # (invalid YAML) raised here and propagated all the way up through
        # setup_schedule() -> main(), crashing the scheduler process before it
        # ever reached its run loop — before ANY routine, including the
        # hardcoded core ones registered earlier in setup_schedule(), could
        # fire. If the container restart-loops on the same broken file, every
        # routine goes silent indefinitely with no error visible anywhere
        # except scheduler logs. Never crash the whole process over the
        # custom-routines file — log loudly and keep going with whatever
        # loaded successfully (core routines are registered before this call,
        # so they're unaffected either way).
        source = "core config" if not is_plugin else f"plugin routines from {config_path}"
        print(f"  ERROR: Failed to load {source} ({config_path}): {e}", flush=True)
        print(f"  Scheduler continuing WITHOUT these routines — fix {config_path} and "
              f"send SIGHUP (or restart) to reload.", flush=True)


def _load_disabled_routines() -> dict[str, set]:
    """Load per-plugin disabled routines from capabilities_disabled column.

    Wave 1.1 (ADR BN-1): open short-lived read-only connection at setup_schedule() time.
    Returns {slug -> set of disabled make-ids} — empty dict if DB unavailable (degrade gracefully).
    """
    result: dict[str, set] = {}
    db_path = WORKSPACE / "dashboard" / "data" / "evonexus.db"
    try:
        import sqlite3 as _sqlite3
        import json as _json
        conn = _sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            "SELECT slug, capabilities_disabled FROM plugins_installed "
            "WHERE enabled = 1 AND status = 'active'"
        ).fetchall()
        conn.close()
        for row in rows:
            try:
                caps = _json.loads(row["capabilities_disabled"] or "{}")
                disabled = caps.get("routines", [])
                if disabled:
                    result[row["slug"]] = set(disabled)
            except Exception:
                pass
    except Exception:
        pass  # DB unavailable — degrade to "nothing disabled", scheduler must not crash
    return result


def _load_custom_routines(schedule):
    """Load custom routines from config/routines.yaml + plugins/*/routines.yaml (ADR-2).

    Wave 1.1: skips plugin routines whose make-id is in capabilities_disabled["routines"].
    """
    # 1. Core config
    _load_routines_from_yaml(schedule, WORKSPACE / "config" / "routines.yaml", is_plugin=False)

    # 2. Plugin routines — sorted for deterministic ordering (ADR-2)
    #    Supports both layouts:
    #      plugins/{slug}/routines.yaml          (flat file)
    #      plugins/{slug}/routines/*.yaml        (directory, GAP-7)
    plugins_dir = WORKSPACE / "plugins"
    if plugins_dir.exists():
        # Wave 1.1: fetch disabled routines once before iterating plugins
        disabled_routines = _load_disabled_routines()

        plugin_routine_files: list[Path] = []
        plugin_routine_files.extend(plugins_dir.glob("*/routines.yaml"))
        plugin_routine_files.extend(plugins_dir.glob("*/routines/*.yaml"))
        for plugin_routines in sorted(plugin_routine_files):
            plugin_slug = plugin_routines.parent.name
            _load_routines_from_yaml(
                schedule, plugin_routines, is_plugin=True,
                disabled_make_ids=disabled_routines.get(plugin_slug, set()),
            )


_monthly_routines = []


def main():
    """Entry point — standalone scheduler."""
    import schedule

    if not acquire_lock():
        sys.exit(1)

    print("EvoNexus Scheduler")
    setup_schedule()
    total = len(schedule.get_jobs())
    print(f"  {total} routines scheduled")
    print(f"  Press Ctrl+C to stop\n")
    recuperar_janelas_perdidas()

    def shutdown(sig, frame):
        release_lock()
        print("\n  Scheduler stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGHUP, _handle_sighup)  # ADR-2: hot-reload on SIGHUP

    monthly_ran = False
    while True:
        # Hot-reload: check flag before running pending jobs (ADR-2)
        if _reload_flag.is_set():
            _reload_flag.clear()
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  {ts} [reload] SIGHUP received — clearing schedule and re-reading routines")
            schedule.clear()
            setup_schedule()
            total = len(schedule.get_jobs())
            print(f"  {ts} [reload] {total} routines scheduled")

        schedule.run_pending()
        now = datetime.now()
        if now.day == 1 and now.hour == 8 and not monthly_ran:
            for r in _monthly_routines:
                if r.get("enabled", True):
                    run_adw(r.get("name", r.get("script", "")), f"custom/{r['script']}", r.get("args", ""))
            monthly_ran = True
        elif now.day != 1:
            monthly_ran = False
        time.sleep(30)


if __name__ == "__main__":
    main()
