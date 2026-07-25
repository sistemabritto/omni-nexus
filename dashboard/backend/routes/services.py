"""Services endpoint — check running background services.

Duas topologias, e a detecção precisa saber em qual está:

- **local**: tudo numa máquina só; os canais rodam em sessões `screen` e o
  scheduler é uma thread do processo do dashboard. `screen -list` responde.
- **swarm/container**: cada serviço é um container próprio
  (evonexus_evonexus_telegram, _scheduler, ...). NÃO existe `screen` — o binário
  nem está instalado na imagem. A checagem antiga por `screen -list` falhava
  sempre e a página mostrava TUDO como "Stopped" enquanto os serviços rodavam
  normalmente. Pior tipo de erro de painel: mentir com confiança.

Em modo container a evidência vem do que os serviços deixam no volume
compartilhado de logs (`ADWs/logs`, montado nos três serviços). Sem socket do
Docker montado — e não vale a pena montar por causa de um indicador — o frescor
do log é o sinal honesto disponível. Quando não há sinal nenhum, o estado é
`unknown`, nunca `stopped`: "não sei" e "está parado" são coisas diferentes.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

from flask import Blueprint, jsonify
from routes._helpers import WORKSPACE

bp = Blueprint("services", __name__)

# Janela para considerar um log "fresco". O heartbeat mais lento roda de 6 em
# 6 horas, então 6h + folga evita falso negativo em serviço ocioso porém vivo.
_LOG_FRESH_SECONDS = int(os.environ.get("SERVICES_LOG_FRESH_SECONDS", str(7 * 3600)))


def _container_mode() -> bool:
    """True quando rodando em container (Swarm/compose), onde `screen` não existe."""
    if (os.environ.get("EVONEXUS_DEPLOY_MODE") or "").lower() in ("swarm", "container", "docker"):
        return True
    if shutil.which("screen"):
        return False
    return Path("/.dockerenv").exists() or Path("/workspace").is_dir()


def _newest_mtime(*globs: str) -> float | None:
    novo = None
    for padrao in globs:
        try:
            for p in Path(WORKSPACE).glob(padrao):
                if p.is_file():
                    m = p.stat().st_mtime
                    novo = m if novo is None or m > novo else novo
        except Exception:  # noqa: BLE001 — indicador nunca derruba a página
            continue
    return novo


def _from_log_evidence(rotulo: str, *globs: str) -> dict:
    """Estado a partir do frescor do log — o sinal disponível sem socket do Docker."""
    m = _newest_mtime(*globs)
    if m is None:
        return {"running": None, "status": "unknown",
                "detail": f"{rotulo}: sem log para inspecionar (gerenciado pelo Swarm)"}
    idade = time.time() - m
    if idade <= _LOG_FRESH_SECONDS:
        mins = int(idade // 60)
        return {"running": True, "status": "running",
                "detail": f"{rotulo}: atividade há {mins} min"}
    horas = int(idade // 3600)
    return {"running": None, "status": "unknown",
            "detail": f"{rotulo}: sem atividade há {horas}h — pode estar ocioso"}


def _check_process(cmd_args: list[str], pipe_grep: str | None = None) -> dict:
    """Check if a process is running using argument-list subprocess calls.

    If pipe_grep is provided, runs cmd_args and filters output for the pattern.
    """
    try:
        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=5)
        output = result.stdout.strip()
        if pipe_grep and output:
            output = "\n".join(l for l in output.splitlines() if pipe_grep in l)
        running = result.returncode == 0 and output != ""
        return {"running": running, "detail": output[:200] if running else ""}
    except Exception:
        return {"running": False, "detail": ""}


def _check_scheduler() -> dict:
    """Check if scheduler thread is running inside the dashboard process."""
    import threading
    for t in threading.enumerate():
        if t.name == "scheduler" and t.is_alive():
            return {"running": True, "detail": "Running (embedded in dashboard)"}
    # Fallback: check for standalone scheduler.py process
    result = _check_process(["ps", "aux"], pipe_grep="scheduler.py")
    return result


def _canal(id_: str, nome: str, descricao: str, comando: str, container: bool) -> dict:
    base = {"id": id_, "name": nome, "description": descricao, "category": "channel"}
    if not container:
        return {**base, "command": comando,
                **_check_process(["screen", "-list"], pipe_grep=id_)}
    # Em Swarm o canal é um serviço próprio: `make ...` não o inicia daqui, então
    # não oferecemos um botão que não funciona.
    return {**base, "managed_by": "swarm",
            **_from_log_evidence(nome, f"ADWs/logs/{id_}*.log", f"ADWs/logs/{id_}/*")}


@bp.route("/api/services")
def list_services():
    container = _container_mode()

    if container:
        scheduler = _from_log_evidence(
            "Scheduler", "ADWs/logs/heartbeats/*.jsonl", "ADWs/logs/*.jsonl")
        scheduler["managed_by"] = "swarm"
    else:
        scheduler = {**_check_scheduler(), "command": "make dashboard-app"}

    services = [
        {
            "id": "scheduler",
            "name": "Scheduler",
            "description": "Automated routines (daily, weekly, monthly) — runs with dashboard",
            **scheduler,
        },
        _canal("telegram", "Telegram Bot",
               "Telegram Channel — receives and responds to messages via Claude",
               "make telegram", container),
        _canal("discord-channel", "Discord Channel",
               "Discord Channel — bidirectional chat bridge with Claude Code",
               "make discord-channel", container),
        _canal("imessage", "iMessage Channel",
               "iMessage Channel — chat with Claude via Messages (macOS)",
               "make imessage", container),
        {
            "id": "dashboard",
            "name": "Dashboard App",
            "description": "This dashboard (React + Flask)",
            # Se esta rota está respondendo, o dashboard está rodando. Perguntar
            # ao `ps` se o processo que atende a requisição existe é teatro — e
            # em container sem `ps` dava "Stopped" na página que a própria app
            # acabou de servir.
            "running": True, "status": "running",
            "detail": "Respondendo a esta requisição",
            **({"managed_by": "swarm"} if container else {"command": "make dashboard-app"}),
        },
    ]

    # Sempre uma lista: mudar a forma da resposta conforme o ambiente quebraria
    # o frontend exatamente no Swarm, que é onde esta correção importa. O modo
    # viaja em cada item, de forma retrocompatível.
    modo = "swarm" if container else "local"
    for s in services:
        s.setdefault("deploy_mode", modo)
        s.setdefault("status", "running" if s.get("running") else "stopped")
    return jsonify(services)


WORKSPACE_STR = str(WORKSPACE)

# ── Manual routine execution ─────────────────────────


@bp.route("/api/routines/<routine_id>/run", methods=["POST"])
def run_routine(routine_id):
    """Manually trigger a routine execution."""
    import shutil
    from pathlib import Path
    from routes._helpers import get_routine_scripts
    routine_scripts = get_routine_scripts()

    script = routine_scripts.get(routine_id)
    if not script:
        # Try matching by script name
        for name, s in routine_scripts.items():
            if routine_id.replace("-", "_") in s or s.replace(".py", "") == routine_id.replace("-", "_"):
                script = s
                break
    if not script:
        return jsonify({"error": f"Unknown routine: {routine_id}"}), 400

    # Validate script path is within ADWs/routines/
    script_path = (WORKSPACE / "ADWs" / "routines" / script).resolve()
    allowed_dir = (WORKSPACE / "ADWs" / "routines").resolve()
    if not str(script_path).startswith(str(allowed_dir)):
        return jsonify({"error": "Invalid script path"}), 400
    if not script_path.exists():
        return jsonify({"error": f"Script not found: {script}"}), 404

    python_bin = shutil.which("uv")
    cmd_args = ["uv", "run", "python", str(script_path)] if python_bin else ["python3", str(script_path)]
    try:
        subprocess.Popen(cmd_args, cwd=WORKSPACE_STR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"status": "started", "routine": routine_id, "script": script})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/services/restart-all", methods=["POST"])
def restart_all_services():
    """Restart all EvoNexus services (dashboard + scheduler + terminal-server).

    Kills processes directly and re-runs start-services.sh, bypassing
    'systemctl restart' which doesn't reliably kill children on Type=oneshot
    services with KillMode=none.
    """
    import shutil
    import os
    workspace = str(WORKSPACE)
    start_script = os.path.join(workspace, "start-services.sh")

    if not os.path.exists(start_script):
        return jsonify({"error": "start-services.sh not found"}), 400

    # Kill existing processes then re-run start-services.sh.
    # sleep 2 gives Flask time to send this response before app.py dies.
    cmd = (
        "sleep 2 && "
        "pkill -f 'terminal-server/bin/server.js' 2>/dev/null; "
        "pkill -f 'python.*scheduler.py' 2>/dev/null; "
        "pkill -f 'python.*app.py' 2>/dev/null; "
        "sleep 1 && "
        f"bash {start_script}"
    )
    subprocess.Popen(
        ["bash", "-c", cmd],
        start_new_session=True,
        cwd=workspace,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return jsonify({"status": "restarting", "message": "Services will restart in ~3 seconds"})


TELEGRAM_LOG = f"{WORKSPACE_STR}/ADWs/logs/telegram.log"
SCHEDULER_LOG = f"{WORKSPACE_STR}/ADWs/logs/scheduler.log"

START_CMDS: dict[str, list[str]] = {
    "scheduler": ["uv", "run", "python", "-u", "scheduler.py"],
    "telegram": ["screen", "-dmS", "telegram", "claude", "--channels", "plugin:telegram@claude-plugins-official", "--dangerously-skip-permissions"],
    "discord-channel": ["screen", "-dmS", "discord-channel", "claude", "--channels", "plugin:discord@claude-plugins-official", "--dangerously-skip-permissions"],
    "imessage": ["screen", "-dmS", "imessage", "claude", "--channels", "plugin:imessage@claude-plugins-official", "--dangerously-skip-permissions"],
}

STOP_CMDS: dict[str, list[str]] = {
    "scheduler": ["pkill", "-f", "scheduler.py"],
    "telegram": ["screen", "-S", "telegram", "-X", "quit"],
    "discord-channel": ["screen", "-S", "discord-channel", "-X", "quit"],
    "imessage": ["screen", "-S", "imessage", "-X", "quit"],
}


@bp.route("/api/services/<service_id>/start", methods=["POST"])
def start_service(service_id):
    cmd_args = START_CMDS.get(service_id)
    if not cmd_args:
        return jsonify({"error": f"Unknown service: {service_id}"}), 400
    try:
        if service_id == "scheduler":
            log_file = open(SCHEDULER_LOG, "a")
            subprocess.Popen(cmd_args, cwd=WORKSPACE_STR, stdout=log_file, stderr=log_file)
        else:
            subprocess.Popen(cmd_args, cwd=WORKSPACE_STR)
        return jsonify({"status": "started", "id": service_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/services/<service_id>/logs")
def service_logs(service_id):
    """Get recent output from a service."""
    if service_id == "telegram":
        from routes._helpers import safe_read

        # Read from log file
        log_path = WORKSPACE / "ADWs" / "logs" / "telegram.log"
        content = safe_read(log_path)
        if content:
            # Clean ANSI escape codes and control chars
            import re
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', content)
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', clean)  # OSC sequences
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', clean)  # control chars
            lines = [l for l in clean.split('\n') if l.strip()]
            if lines:
                return jsonify({"lines": lines[-200:]})

        # Check if running but no log yet
        try:
            result = _check_process(["screen", "-list"], pipe_grep="telegram")
            if result["running"]:
                return jsonify({"lines": [
                    "Telegram bot is running.",
                    "Log file will populate as messages are processed.",
                    "",
                    "If started before this update, restart with Stop → Start",
                    "to enable logging.",
                    "",
                    f"Screen: {result['detail']}",
                ]})
        except Exception:
            pass

        return jsonify({"lines": ["Telegram bot is not running. Click Start to launch it."]})

    elif service_id == "scheduler":
        from routes._helpers import safe_read

        # Read real scheduler process output
        log_path = WORKSPACE / "ADWs" / "logs" / "scheduler.log"
        content = safe_read(log_path)
        if content:
            import re
            # Clean ANSI escape codes and control chars (Rich output)
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', content)
            clean = re.sub(r'\x1b\][^\x07]*\x07', '', clean)  # OSC sequences
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', clean)  # control chars
            lines = [l for l in clean.split('\n') if l.strip()]
            if lines:
                return jsonify({"lines": lines[-200:]})

        # Check if running but no log yet
        try:
            result = _check_process(["ps", "aux"], pipe_grep="scheduler.py")
            if result["running"]:
                return jsonify({"lines": [
                    "Scheduler is running.",
                    "Log file will populate as routines execute.",
                    "",
                    "If started before this update, restart with Stop → Start",
                    "to enable log capture.",
                ]})
        except Exception:
            pass

        return jsonify({"lines": ["Scheduler is not running. Click Start to launch it."]})

    elif service_id in ("discord-channel", "imessage"):
        screen_name = service_id
        label = "Discord channel" if service_id == "discord-channel" else "iMessage channel"
        try:
            result = _check_process(["screen", "-list"], pipe_grep=screen_name)
            if result["running"]:
                return jsonify({"lines": [
                    f"{label} is running.",
                    "Logs are available in the screen session.",
                    f"Attach with: make {screen_name}-attach",
                    "",
                    f"Screen: {result['detail']}",
                ]})
        except Exception:
            pass
        return jsonify({"lines": [f"{label} is not running. Click Start to launch it."]})

    return jsonify({"error": "Unknown service"}), 400


@bp.route("/api/services/<service_id>/stop", methods=["POST"])
def stop_service(service_id):
    cmd_args = STOP_CMDS.get(service_id)
    if not cmd_args:
        return jsonify({"error": f"Unknown service: {service_id}"}), 400
    try:
        subprocess.run(cmd_args, timeout=5, stderr=subprocess.DEVNULL)
        return jsonify({"status": "stopped", "id": service_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
