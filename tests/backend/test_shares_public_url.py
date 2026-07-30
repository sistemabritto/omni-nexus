"""routes/shares.py::_public_base_url — NEXUS_PUBLIC_URL precisa vencer o
Host da requisição.

Achado ao vivo em 29/07/2026: o ticket de aprovação dos cortes virais saiu
com link http://evonexus-dashboard:8080/share/..., o hostname interno do
service mesh — porque quem cria o share é o media_worker via sdk_client, e
`request.host_url` reflete o Host de quem chamou, não o domínio público.
NEXUS_PUBLIC_URL já estava documentado em .env.example pra esse cenário, só
nunca tinha sido lido pelo código.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routes.shares import _public_base_url  # noqa: E402


def test_nexus_public_url_vence_o_host_da_requisicao(monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_URL", "https://nexus.workflowapi.com.br/")
    # não precisa de contexto de request do Flask — a env var faz o `or`
    # curto-circuitar antes de request.host_url ser avaliado.
    assert _public_base_url() == "https://nexus.workflowapi.com.br"


def test_ngrok_url_e_o_fallback_quando_nexus_public_url_nao_esta_setado(monkeypatch):
    monkeypatch.delenv("NEXUS_PUBLIC_URL", raising=False)
    monkeypatch.setenv("NGROK_URL", "https://abc123.ngrok.io")
    assert _public_base_url() == "https://abc123.ngrok.io"
