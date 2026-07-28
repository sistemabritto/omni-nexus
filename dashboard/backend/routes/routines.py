"""Routines endpoint — metrics, logs, and ADW scripts."""

import ast
import json
from datetime import date
from flask import Blueprint, jsonify, request
from routes._helpers import WORKSPACE, safe_read

bp = Blueprint("routines", __name__)

METRICS_PATH = WORKSPACE / "ADWs" / "logs" / "metrics.json"
LOGS_DIR = WORKSPACE / "ADWs" / "logs"
ROTINAS_DIR = WORKSPACE / "ADWs" / "routines"


@bp.route("/api/routines")
def get_routines():
    content = safe_read(METRICS_PATH)
    data: dict = {}
    if content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}

    # Merge in routines that are declared (ADWs/ or plugins/) but haven't
    # run yet — so plugin rotinas, custom rotinas recém-adicionadas and
    # core scripts without history all appear in the UI with zeroed metrics.
    try:
        from routes._helpers import discover_routines
        discovered = discover_routines()
    except Exception:
        discovered = {}

    # O runner grava a métrica com o nome da rotina em kebab (`good-morning`),
    # e `discover_routines` inventa um id abreviado para o Makefile
    # (`good_morning` → `morning`). São chaves diferentes para a MESMA rotina:
    # sem fundir, a tela mostra "Good Morning, 25 execuções" e logo abaixo
    # "Morning, 0 execuções" — metade da lista era esse fantasma, e não havia
    # como saber qual das duas linhas era a real.
    for make_id, spec in list(discovered.items()):
        kebab = (spec.get("script") or "").replace("custom/", "").replace(".py", "").replace("_", "-")
        if kebab and kebab != make_id and kebab in data and make_id not in data:
            discovered[make_id] = {**spec, "_alias_de": kebab}

    for make_id, spec in discovered.items():
        if spec.get("_alias_de"):
            # Já existe com a chave que o runner usa; só enriquece aquela.
            entry = data.get(spec["_alias_de"])
            if isinstance(entry, dict):
                entry.setdefault("agent", spec.get("agent", ""))
                entry["name"] = spec.get("name") or spec["_alias_de"]
                entry["script"] = spec.get("script", "")
            continue
        if make_id in data:
            # already has execution metrics; enrich with agent/name if missing
            entry = data[make_id]
            if isinstance(entry, dict):
                entry.setdefault("agent", spec.get("agent", ""))
                entry.setdefault("source_plugin", spec.get("source_plugin"))
                # O script é o que liga a métrica ao arquivo — sem ele não dá
                # para dizer se a rotina chama modelo nem para casar esta linha
                # com o agendamento na tela.
                entry.setdefault("name", spec.get("name", ""))
                entry.setdefault("script", spec.get("script", ""))
            continue
        data[make_id] = {
            "agent": spec.get("agent", ""),
            "name": spec.get("name", ""),
            "script": spec.get("script", ""),
            "runs": 0,
            "successes": 0,
            "success_rate": 0,
            "avg_seconds": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "avg_cost_usd": 0.0,
            "last_run": None,
            "source_plugin": spec.get("source_plugin"),
        }

    # Motor de cada rotina: Python determinístico ou chamada de modelo. É a
    # diferença entre uma rotina que custa CPU e uma que custa dinheiro a cada
    # execução, e é o que decide se ela pode rodar de 15 em 15 minutos.
    try:
        from routines_registry import motor_do_script

        for val in data.values():
            if isinstance(val, dict):
                val["engine"] = motor_do_script(val.get("script") or "")
    except Exception:  # noqa: BLE001 — sem o rótulo a página ainda serve
        pass

    # Totais somados das chaves que existem de verdade.
    #
    # Estava lendo `val["cost"]` e `val["tokens"]`, que o runner nunca gravou —
    # ele grava `total_cost_usd` e `total_input_tokens`/`total_output_tokens`.
    # O painel exibia custo zero e zero token com US$ 27 e milhões de tokens no
    # arquivo. Um número errado com cara de número certo é pior que campo vazio:
    # não dá para desconfiar dele.
    totals = {"total_runs": 0, "total_cost": 0.0, "total_tokens": 0}
    for val in data.values():
        if not isinstance(val, dict):
            continue
        totals["total_runs"] += val.get("runs", 0) or 0
        totals["total_cost"] += val.get("total_cost_usd", 0.0) or 0.0
        totals["total_tokens"] += ((val.get("total_input_tokens", 0) or 0)
                                   + (val.get("total_output_tokens", 0) or 0))
    totals["total_cost"] = round(totals["total_cost"], 4)

    return jsonify({"metrics": data, "totals": totals})


@bp.route("/api/routines/logs")
def get_routine_logs():
    target = request.args.get("date", date.today().isoformat())
    # Look for JSONL files matching the date
    entries = []
    if LOGS_DIR.is_dir():
        for f in LOGS_DIR.iterdir():
            if f.suffix == ".jsonl" and target in f.name:
                text = safe_read(f)
                if text:
                    for line in text.strip().splitlines():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        # Also check a generic log file
        generic = LOGS_DIR / f"{target}.jsonl"
        if generic.is_file():
            text = safe_read(generic)
            if text:
                for line in text.strip().splitlines():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return jsonify(entries)


@bp.route("/api/routines/adws")
def list_adws():
    if not ROTINAS_DIR.is_dir():
        return jsonify([])
    scripts = []
    for f in sorted(ROTINAS_DIR.iterdir()):
        if f.suffix == ".py" and f.is_file():
            doc = ""
            text = safe_read(f)
            if text:
                try:
                    tree = ast.parse(text)
                    raw = ast.get_docstring(tree)
                    if raw:
                        doc = raw.splitlines()[0]
                except SyntaxError:
                    pass
            scripts.append({"name": f.stem, "file": f.name, "description": doc})
    return jsonify(scripts)


# Pricing per model for image generation (USD)
# Format: { model_substring: { per_image: float, input_per_1m: float, output_per_1m: float } }
IMAGE_MODEL_PRICING = {
    "gemini-3.1-flash-image-preview": {"per_image": 0.039, "input_per_1m": 0.075, "output_per_1m": 0.30},
    "gemini-2.0-flash": {"per_image": 0.039, "input_per_1m": 0.10, "output_per_1m": 0.40},
    "flux-2": {"per_image": 0.03, "input_per_1m": 0, "output_per_1m": 0},
    "flux.2": {"per_image": 0.03, "input_per_1m": 0, "output_per_1m": 0},
    "gpt-5-image": {"per_image": 0.04, "input_per_1m": 0.005, "output_per_1m": 0.015},
    # OpenAI Images API — billed per token (text input / image output rates).
    "gpt-image-2": {"per_image": 0.0, "input_per_1m": 5.0, "output_per_1m": 40.0},
    "seedream": {"per_image": 0.02, "input_per_1m": 0, "output_per_1m": 0},
    "riverflow": {"per_image": 0.02, "input_per_1m": 0, "output_per_1m": 0},
}


def _estimate_image_cost(entry: dict) -> float:
    """Estimate USD cost for a single image generation entry."""
    model = entry.get("model", "").lower()
    tokens = entry.get("token_usage", {})
    total_tokens = tokens.get("total_tokens", 0)

    # Find matching pricing by model substring
    pricing = None
    for key, p in IMAGE_MODEL_PRICING.items():
        if key in model:
            pricing = p
            break

    if not pricing:
        # Fallback: assume $0.03/image for unknown models
        return 0.03

    cost = pricing["per_image"]
    prompt_tokens = tokens.get("prompt_tokens", 0)
    completion_tokens = tokens.get("completion_tokens", 0)
    if prompt_tokens and completion_tokens and pricing.get("output_per_1m", 0) > 0:
        # Split billing: text input vs image output rates (OpenAI Images API)
        cost += (prompt_tokens / 1_000_000) * pricing["input_per_1m"]
        cost += (completion_tokens / 1_000_000) * pricing["output_per_1m"]
    elif total_tokens > 0 and pricing["input_per_1m"] > 0:
        cost += (total_tokens / 1_000_000) * pricing["input_per_1m"]
    return round(cost, 6)


@bp.route("/api/routines/image-costs")
def get_image_costs():
    """Return AI image generation cost entries with estimated costs."""
    costs_path = LOGS_DIR / "ai-image-creator-costs.json"
    content = safe_read(costs_path)
    if not content:
        return jsonify({"entries": [], "totals": {}})
    try:
        entries = json.loads(content)
    except json.JSONDecodeError:
        return jsonify({"entries": [], "totals": {}})

    total_tokens = 0
    total_seconds = 0.0
    total_bytes = 0
    total_cost = 0.0
    for e in entries:
        tokens = e.get("token_usage", {})
        total_tokens += tokens.get("total_tokens", 0)
        total_seconds += e.get("elapsed_seconds", 0)
        total_bytes += e.get("size_bytes", 0)
        est = _estimate_image_cost(e)
        e["estimated_cost_usd"] = est
        total_cost += est

    return jsonify({
        "entries": entries,
        "totals": {
            "count": len(entries),
            "total_tokens": total_tokens,
            "total_seconds": round(total_seconds, 1),
            "total_bytes": total_bytes,
            "total_cost_usd": round(total_cost, 4),
        },
    })
