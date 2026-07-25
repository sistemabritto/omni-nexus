"""MCP Servers listing — Wave 2.3 UI.

Read-only view of every MCP server configurado para este workspace,
cruzado com `plugins_installed` para a UI saber quais entradas vieram de um
plugin do EvoNexus e quais são nativas / mantidas à mão.

Duas fontes, porque o Claude Code tem dois escopos e a página mostrava só um:

* **projeto** — `.mcp.json` na raiz do repositório. É onde os MCPs de verdade
  do workspace moram, é versionado no fork e portanto igual em toda máquina que
  rode a imagem. Era a fonte que faltava: a página lia apenas `~/.claude.json`
  e por isso aparecia vazia na VPS mesmo com dez servidores configurados.
* **usuário** — `~/.claude.json` em `projects[WORKSPACE].mcpServers`. É onde o
  instalador de plugins injeta (`plugin_claude_config`) e onde a CLI grava
  quando o usuário adiciona um MCP à mão. Na VPS esse arquivo é recriado a cada
  redeploy, então nada que só viva nele sobrevive — mais um motivo para o
  `.mcp.json` ser a fonte estável.

Quando o mesmo nome existe nos dois escopos, o de usuário vence: é o que o
Claude Code de fato usa, e uma página de diagnóstico que mostra a configuração
perdedora é pior que não mostrar nada.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify
from flask_login import login_required

from plugin_claude_config import CLAUDE_JSON, WORKSPACE

bp = Blueprint("mcp_servers", __name__)

DB_PATH = WORKSPACE / "dashboard" / "data" / "evonexus.db"
PROJECT_MCP_JSON = WORKSPACE / ".mcp.json"


def _plugin_mcp_ownership() -> dict[str, str]:
    """Return {effective_mcp_name: plugin_slug} for every installed plugin
    that tracks MCPs in its manifest_json.
    """
    ownership: dict[str, str] = {}
    if not DB_PATH.exists():
        return ownership
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT slug, manifest_json FROM plugins_installed WHERE enabled = 1"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return ownership
    for row in rows:
        try:
            manifest = json.loads(row["manifest_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        installed = manifest.get("mcp_servers_installed") or []
        for entry in installed:
            name = entry.get("effective_name") if isinstance(entry, dict) else None
            if name:
                ownership[name] = row["slug"]
    return ownership


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """(conteúdo, erro). Arquivo ausente devolve (None, None) — não é erro."""
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_bytes()), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"{path}: {exc}"


def _project_servers() -> tuple[dict[str, Any], str | None]:
    data, erro = _read_json(PROJECT_MCP_JSON)
    if not data:
        return {}, erro
    servers = data.get("mcpServers")
    return (servers if isinstance(servers, dict) else {}), erro


def _user_servers() -> tuple[dict[str, Any], str | None]:
    """Entradas de `projects[WORKSPACE].mcpServers` em ~/.claude.json.

    A chave é o caminho absoluto do workspace, que difere entre a máquina local
    e o container (`/workspace`). Buscamos a chave exata e, se ela não existir,
    aceitamos uma única entrada de projeto — o container só tem uma, e falhar
    por diferença de caminho esconderia MCPs que existem de verdade.
    """
    data, erro = _read_json(CLAUDE_JSON)
    if not data:
        return {}, erro
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return {}, erro
    entry = projects.get(str(WORKSPACE.resolve()))
    if entry is None and len(projects) == 1:
        entry = next(iter(projects.values()))
    servers = (entry or {}).get("mcpServers")
    return (servers if isinstance(servers, dict) else {}), erro


def _describe(name: str, cfg: dict, scope: str, ownership: dict[str, str]) -> dict[str, Any]:
    """Normaliza as duas formas de transporte numa entrada só para a UI.

    Um MCP é `stdio` (command + args) ou `http`/`sse` (url). A página só
    conhecia a primeira e mostrava "—" para as dez entradas HTTP do workspace,
    que é justamente o transporte de todos eles.
    """
    transport = (cfg.get("type") or ("http" if cfg.get("url") else "stdio")).lower()
    source_plugin = ownership.get(name)
    return {
        "name": name,
        "transport": transport,
        "url": cfg.get("url"),
        "command": cfg.get("command"),
        "args": cfg.get("args") or [],
        "env": cfg.get("env") or {},
        "scope": scope,
        "source": "plugin" if source_plugin else "native",
        "source_plugin": source_plugin,
    }


@bp.route("/api/mcp-servers", methods=["GET"])
@login_required
def list_mcp_servers():
    """Lista os MCP servers configurados para este workspace.

    Response shape:
        {
            "workspace": "/abs/path",
            "claude_json_exists": bool,
            "sources": [{"scope","path","exists","count"}],
            "servers": [
                {
                    "name": "plugin-open-seo-openseo",
                    "transport": "http" | "stdio" | "sse",
                    "url": "http://openseo:3001/mcp" | null,
                    "command": "npx" | null,
                    "args": [...], "env": {...},
                    "scope": "project" | "user",
                    "source": "plugin" | "native",
                    "source_plugin": "open-seo" | null
                }
            ]
        }
    """
    ws_abs = str(WORKSPACE.resolve())
    projeto, erro_projeto = _project_servers()
    usuario, erro_usuario = _user_servers()
    ownership = _plugin_mcp_ownership()

    # Usuário vence projeto no mesmo nome: é a entrada que o Claude Code usa.
    combinado: dict[str, tuple[dict, str]] = {n: (c, "project") for n, c in projeto.items()
                                              if isinstance(c, dict)}
    combinado.update({n: (c, "user") for n, c in usuario.items() if isinstance(c, dict)})

    servers = [_describe(n, cfg, scope, ownership) for n, (cfg, scope) in combinado.items()]

    # Plugin primeiro (agrupado por slug), depois nativo — ordem estável.
    servers.sort(key=lambda s: (
        0 if s["source"] == "plugin" else 1,
        s["source_plugin"] or "",
        s["name"],
    ))

    erros = [e for e in (erro_projeto, erro_usuario) if e]
    body: dict[str, Any] = {
        "workspace": ws_abs,
        # Mantido pelo contrato antigo do frontend; hoje o vazio que importa é
        # o de `servers`, já que o .mcp.json sozinho basta para a página servir.
        "claude_json_exists": CLAUDE_JSON.exists(),
        "claude_json_path": str(CLAUDE_JSON),
        "sources": [
            {"scope": "project", "path": str(PROJECT_MCP_JSON),
             "exists": PROJECT_MCP_JSON.exists(), "count": len(projeto)},
            {"scope": "user", "path": str(CLAUDE_JSON),
             "exists": CLAUDE_JSON.exists(), "count": len(usuario)},
        ],
        "servers": servers,
    }
    if erros:
        body["error"] = "; ".join(erros)
    return jsonify(body)
