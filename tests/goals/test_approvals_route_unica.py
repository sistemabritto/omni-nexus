"""
tests/goals/test_approvals_route_unica.py

A página /approvals mostrava "nenhuma aprovação" com uma aprovação pendente de
verdade no banco (validação com o Felipe, 25/07/2026).

Causa: DOIS blueprints registravam `GET /api/approvals`. O de heartbeats.py
lia a tabela legada `approval_queue`, que não tem produtor nenhum — nada
escreve nela desde que os gates passaram a viver em `pending_approvals`. Como
`heartbeats_bp` é registrado antes de `approvals_bp` em app.py, o Flask mantém
a primeira regra e era a morta que atendia. A resposta nem tinha a mesma forma
(`{"pending": [], "stats": {}}` contra `{"approvals": [...]}`), então o
frontend lia `data.approvals` de um objeto que não tinha esse campo e
renderizava a lista vazia sem nenhum erro visível.

Um gate que ninguém vê é um gate que não existe: o Telegram avisava, a página
dizia que não havia nada, e as duas coisas eram "o sistema funcionando".

Run:
    pytest tests/goals/test_approvals_route_unica.py -v
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND))


def _rotas_declaradas(arquivo: Path) -> list[tuple[str, str]]:
    """(caminho, métodos) de cada @bp.route do arquivo, sem importar nada."""
    fonte = arquivo.read_text(encoding="utf-8")
    achados = []
    for m in re.finditer(r'@bp\.route\(\s*"([^"]+)"([^)]*)\)', fonte):
        caminho, resto = m.group(1), m.group(2)
        metodos = re.findall(r'"(GET|POST|PATCH|PUT|DELETE)"', resto) or ["GET"]
        for metodo in metodos:
            achados.append((caminho, metodo))
    return achados


def test_nenhum_outro_blueprint_registra_get_api_approvals():
    """O defeito não era a fila legada estar vazia — era existirem duas rotas
    com o mesmo caminho, e a errada ganhar por ordem de registro."""
    donos = []
    for arquivo in sorted((BACKEND / "routes").glob("*.py")):
        for caminho, metodo in _rotas_declaradas(arquivo):
            if caminho == "/api/approvals" and metodo == "GET":
                donos.append(arquivo.name)
    assert donos == ["approvals.py"], (
        f"GET /api/approvals declarado em {donos} — só approvals.py pode declarar; "
        "duplicata volta a sombrear a implementação real"
    )


def test_heartbeats_nao_declara_mais_rota_de_aprovacao():
    caminhos = [c for c, _ in _rotas_declaradas(BACKEND / "routes" / "heartbeats.py")]
    assert not [c for c in caminhos if c.startswith("/api/approvals")]


def test_app_nao_tem_regra_de_url_duplicada():
    """Rede de segurança geral: qualquer caminho+método declarado duas vezes é
    uma rota silenciosamente inalcançável esperando para morder."""
    vistos: dict[tuple[str, str], str] = {}
    duplicadas = []
    for arquivo in sorted((BACKEND / "routes").glob("*.py")):
        for chave in _rotas_declaradas(arquivo):
            if chave in vistos and vistos[chave] != arquivo.name:
                duplicadas.append(f"{chave[1]} {chave[0]}: {vistos[chave]} e {arquivo.name}")
            vistos.setdefault(chave, arquivo.name)
    assert not duplicadas, "rotas duplicadas entre blueprints:\n  " + "\n  ".join(duplicadas)


def test_a_forma_da_resposta_e_a_que_o_frontend_le():
    """O frontend faz `data.approvals || []`. Uma resposta com outra forma não
    dá erro nenhum — só mostra a lista vazia para sempre."""
    fonte = (BACKEND / "routes" / "approvals.py").read_text(encoding="utf-8")
    assert '"approvals":' in fonte

    tsx = (REPO_ROOT / "dashboard" / "frontend" / "src" / "pages" / "Approvals.tsx").read_text(
        encoding="utf-8")
    assert "data.approvals" in tsx, "se o frontend mudar de campo, este teste tem que mudar junto"
