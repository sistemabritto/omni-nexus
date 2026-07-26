"""
tests/backend/test_plugins_no_disco.py

2026-07-26 — /plugins jurava que não havia plugin instalado.

A tabela `plugins_installed` só ganha linha quando alguém instala pela UI.
O open-seo veio versionado no repo, alimenta o research semanal toda semana, e
a página listava vazio — porque lia o histórico de cliques em vez do disco.

Run:
    pytest tests/backend/test_plugins_no_disco.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

import routes.plugins as mod  # noqa: E402


@pytest.fixture
def raiz(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "PLUGINS_DIR", tmp_path)
    return tmp_path


def _plugin(raiz: Path, slug: str, manifesto: str | None = None) -> Path:
    pasta = raiz / slug
    pasta.mkdir()
    if manifesto is not None:
        (pasta / "plugin.yaml").write_text(manifesto, encoding="utf-8")
    return pasta


def test_encontra_plugin_versionado_no_repo(raiz):
    _plugin(raiz, "open-seo", "id: open-seo\nname: OpenSEO\nversion: 1.0.0\n"
                              "description: camada de SEO\ntier: essential\n"
                              "capabilities:\n  - skills\n")
    achados = mod._plugins_no_disco()
    assert len(achados) == 1
    assert achados[0]["slug"] == "open-seo"
    assert achados[0]["name"] == "OpenSEO"
    assert achados[0]["capabilities"] == ["skills"]


def test_marca_como_nao_registrado(raiz):
    """Está no disco e funciona, mas não tem checksum nem histórico de update —
    esconder essa diferença seria pior que mostrá-la."""
    _plugin(raiz, "open-seo", "id: open-seo\nname: OpenSEO\nversion: 1.0.0\n")
    assert mod._plugins_no_disco()[0]["status"] == "present_unregistered"


def test_pasta_sem_manifesto_ainda_aparece(raiz):
    """Existir no disco é o fato; o manifesto só enriquece a descrição."""
    _plugin(raiz, "sem-manifesto")
    achados = mod._plugins_no_disco()
    assert achados[0]["slug"] == "sem-manifesto"
    assert achados[0]["version"] == "?"


def test_manifesto_quebrado_nao_esconde_a_pasta(raiz):
    _plugin(raiz, "quebrado", "isto: [não é\n  yaml: válido: {")
    assert [p["slug"] for p in mod._plugins_no_disco()] == ["quebrado"]


def test_arquivo_solto_nao_vira_plugin(raiz):
    (raiz / "README.md").write_text("não sou plugin", encoding="utf-8")
    assert mod._plugins_no_disco() == []


def test_diretorio_ausente_devolve_lista_vazia(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "PLUGINS_DIR", tmp_path / "nao-existe")
    assert mod._plugins_no_disco() == []


def test_ordem_e_estavel(raiz):
    for slug in ("zulu", "alfa", "mike"):
        _plugin(raiz, slug)
    assert [p["slug"] for p in mod._plugins_no_disco()] == ["alfa", "mike", "zulu"]
