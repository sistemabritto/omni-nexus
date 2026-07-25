"""
tests/backend/test_mcp_servers_sources.py

A página /mcp-servers aparecia vazia na VPS com dez MCPs configurados
(print do Felipe, 25/07/2026).

Duas causas somadas:

1. A rota lia só `~/.claude.json` -> `projects[WORKSPACE].mcpServers`. Os MCPs
   de verdade do workspace moram em `.mcp.json` na raiz do repo (escopo de
   projeto), que a rota ignorava. No container o ~/.claude.json é recriado a
   cada redeploy e volta com `mcpServers: {}` — então a única fonte que a
   página lia era justamente a que não sobrevive.
2. A rota (e a UI) só conheciam o transporte stdio (command + args). Todos os
   dez servidores são `type: "http"` com `url`, então mesmo lidos apareceriam
   sem identificação nenhuma.

Run:
    pytest tests/backend/test_mcp_servers_sources.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routes import mcp_servers as M  # noqa: E402


MCP_PROJETO = {
    "mcpServers": {
        "plugin-open-seo-openseo": {"type": "http", "url": "http://openseo:3001/mcp"},
        "linear-server": {"type": "http", "url": "https://mcp.linear.app/mcp"},
    }
}


@pytest.fixture
def fontes(tmp_path, monkeypatch):
    """Aponta as duas fontes para arquivos temporários e devolve escritores."""
    projeto = tmp_path / ".mcp.json"
    usuario = tmp_path / "claude.json"
    monkeypatch.setattr(M, "PROJECT_MCP_JSON", projeto)
    monkeypatch.setattr(M, "CLAUDE_JSON", usuario)
    monkeypatch.setattr(M, "WORKSPACE", tmp_path)
    monkeypatch.setattr(M, "_plugin_mcp_ownership", dict)

    def escrever_projeto(dados):
        projeto.write_text(json.dumps(dados), encoding="utf-8")

    def escrever_usuario(mcp, chave=None):
        usuario.write_text(json.dumps(
            {"projects": {chave or str(tmp_path): {"mcpServers": mcp}}}), encoding="utf-8")

    return escrever_projeto, escrever_usuario


@pytest.fixture
def cliente(fontes):
    from flask import Flask

    app = Flask(__name__)
    # A rota é @login_required; o alvo aqui é a leitura das fontes, não o auth.
    app.view_functions.clear()
    bp = M.bp
    app.add_url_rule("/api/mcp-servers", "mcp",
                     M.list_mcp_servers.__wrapped__, methods=["GET"])
    assert bp is not None
    return app.test_client(), *fontes


# ── a fonte que faltava ──────────────────────────────────────────────────

def test_le_os_mcps_do_mcp_json_do_projeto(cliente):
    c, escrever_projeto, _ = cliente
    escrever_projeto(MCP_PROJETO)
    body = c.get("/api/mcp-servers").get_json()
    nomes = {s["name"] for s in body["servers"]}
    assert nomes == {"plugin-open-seo-openseo", "linear-server"}


def test_sem_claude_json_a_pagina_ainda_serve(cliente):
    """O caso da VPS: ~/.claude.json some no redeploy e o .mcp.json basta."""
    c, escrever_projeto, _ = cliente
    escrever_projeto(MCP_PROJETO)
    body = c.get("/api/mcp-servers").get_json()
    assert body["claude_json_exists"] is False
    assert len(body["servers"]) == 2, "arquivo de usuário ausente não pode zerar a lista"


def test_junta_os_dois_escopos(cliente):
    c, escrever_projeto, escrever_usuario = cliente
    escrever_projeto(MCP_PROJETO)
    escrever_usuario({"plugin-pm-filesystem": {"command": "npx", "args": ["-y", "fs"]}})
    body = c.get("/api/mcp-servers").get_json()
    assert len(body["servers"]) == 3
    por_nome = {s["name"]: s for s in body["servers"]}
    assert por_nome["linear-server"]["scope"] == "project"
    assert por_nome["plugin-pm-filesystem"]["scope"] == "user"


def test_escopo_de_usuario_vence_no_mesmo_nome(cliente):
    """É a entrada que o Claude Code realmente usa — mostrar a perdedora seria
    pior que não mostrar nada."""
    c, escrever_projeto, escrever_usuario = cliente
    escrever_projeto({"mcpServers": {"linear-server": {"type": "http", "url": "https://antigo/mcp"}}})
    escrever_usuario({"linear-server": {"type": "http", "url": "https://novo/mcp"}})
    body = c.get("/api/mcp-servers").get_json()
    assert len(body["servers"]) == 1
    assert body["servers"][0]["url"] == "https://novo/mcp"
    assert body["servers"][0]["scope"] == "user"


def test_caminho_do_workspace_diferente_ainda_encontra(cliente, tmp_path):
    """No container o workspace é /workspace; a chave gravada pode ser outra.
    Falhar por diferença de caminho esconderia MCPs que existem."""
    c, _, escrever_usuario = cliente
    escrever_usuario({"gmail": {"type": "http", "url": "https://gmail/mcp"}},
                     chave="/caminho/de/outra/maquina")
    body = c.get("/api/mcp-servers").get_json()
    assert {s["name"] for s in body["servers"]} == {"gmail"}


def test_varios_projetos_no_claude_json_nao_vazam(cliente, tmp_path):
    """Aceitar 'a única entrada' é o fallback; com várias, sem correspondência
    exata, não se pode adivinhar qual é a deste workspace."""
    c, _, _ = cliente
    M.CLAUDE_JSON.write_text(json.dumps({"projects": {
        "/um": {"mcpServers": {"a": {"type": "http", "url": "https://a"}}},
        "/dois": {"mcpServers": {"b": {"type": "http", "url": "https://b"}}},
    }}), encoding="utf-8")
    assert c.get("/api/mcp-servers").get_json()["servers"] == []


# ── transporte ───────────────────────────────────────────────────────────

def test_http_expoe_url_e_transporte(cliente):
    c, escrever_projeto, _ = cliente
    escrever_projeto(MCP_PROJETO)
    s = next(x for x in c.get("/api/mcp-servers").get_json()["servers"]
             if x["name"] == "linear-server")
    assert s["transport"] == "http"
    assert s["url"] == "https://mcp.linear.app/mcp"
    assert s["command"] is None


def test_stdio_continua_com_command_e_args(cliente):
    c, _, escrever_usuario = cliente
    escrever_usuario({"fs": {"command": "npx", "args": ["-y", "server-fs"], "env": {"K": "v"}}})
    s = c.get("/api/mcp-servers").get_json()["servers"][0]
    assert s["transport"] == "stdio"
    assert s["command"] == "npx" and s["args"] == ["-y", "server-fs"]
    assert s["url"] is None


def test_transporte_inferido_quando_o_type_falta(cliente):
    c, escrever_projeto, _ = cliente
    escrever_projeto({"mcpServers": {"x": {"url": "https://x/mcp"}}})
    assert c.get("/api/mcp-servers").get_json()["servers"][0]["transport"] == "http"


# ── robustez ─────────────────────────────────────────────────────────────

def test_json_quebrado_reporta_erro_sem_derrubar_a_outra_fonte(cliente):
    c, _, escrever_usuario = cliente
    M.PROJECT_MCP_JSON.write_text("{ não é json", encoding="utf-8")
    escrever_usuario({"gmail": {"type": "http", "url": "https://gmail/mcp"}})
    body = c.get("/api/mcp-servers").get_json()
    assert "error" in body
    assert {s["name"] for s in body["servers"]} == {"gmail"}


def test_nenhuma_fonte_devolve_lista_vazia_sem_erro(cliente):
    c, _, _ = cliente
    body = c.get("/api/mcp-servers").get_json()
    assert body["servers"] == [] and "error" not in body


def test_sources_declara_os_dois_escopos_com_contagem(cliente):
    c, escrever_projeto, _ = cliente
    escrever_projeto(MCP_PROJETO)
    fontes = {f["scope"]: f for f in c.get("/api/mcp-servers").get_json()["sources"]}
    assert fontes["project"]["exists"] is True and fontes["project"]["count"] == 2
    assert fontes["user"]["exists"] is False and fontes["user"]["count"] == 0


def test_mcp_json_do_repo_e_valido_e_entra_na_imagem():
    """O arquivo real precisa existir, ser válido e estar no Dockerfile —
    sem o COPY o container fica sem MCP nenhum, que era o estado da VPS."""
    real = REPO_ROOT / ".mcp.json"
    assert real.exists(), ".mcp.json some do repo = workspace sem MCP"
    assert json.loads(real.read_text(encoding="utf-8")).get("mcpServers")
    dockerfile = (REPO_ROOT / "Dockerfile.swarm.dashboard").read_text(encoding="utf-8")
    assert ".mcp.json" in dockerfile, "sem COPY .mcp.json o container não recebe os MCPs"
