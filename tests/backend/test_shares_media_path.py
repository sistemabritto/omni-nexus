"""shares._resolve_path_safe também aceita caminhos em MEDIA_WORKSPACE.

Fase 1B da esteira de vídeo: a página de revisão do corte editorial nasce no
workspace do MediaJob (volume separado de workspace/), e sem essa segunda
raiz permitida não haveria como transformá-la num link — ver routes/shares.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

from routes.shares import _resolve_path_safe  # noqa: E402


def test_aceita_caminho_dentro_de_workspace():
    resolvido = _resolve_path_safe("workspace/reports/x.html")
    assert resolvido is not None
    assert str(resolvido).endswith("workspace/reports/x.html")


def test_aceita_caminho_dentro_de_media():
    resolvido = _resolve_path_safe("media/jobs/abc-123/output/revisao.html")
    assert resolvido is not None
    assert str(resolvido).endswith("media/jobs/abc-123/output/revisao.html")


def test_recusa_path_absoluto():
    assert _resolve_path_safe("/etc/passwd") is None


def test_recusa_traversal_pra_fora_das_duas_raizes():
    assert _resolve_path_safe("workspace/../config/.env") is None
    assert _resolve_path_safe("media/../config/.env") is None


def test_recusa_pasta_que_nao_e_nenhuma_das_duas_raizes():
    assert _resolve_path_safe("dashboard/backend/app.py") is None
