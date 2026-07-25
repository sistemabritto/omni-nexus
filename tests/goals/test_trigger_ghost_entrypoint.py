"""
tests/goals/test_trigger_ghost_entrypoint.py

O trigger "Ghost publicou -> distribuir nas redes" estava criado e habilitado,
mas não podia funcionar por dois motivos independentes:

1. `action_payload` apontava para `scripts/ghost_published_to_social.py`. O
   executor resolve todo script dentro de `ADWs/routines/` — fronteira de
   segurança deliberada — então o caminho virava
   `ADWs/routines/scripts/ghost_published_to_social.py`, que não existe.
2. A ação `script` nunca recebia o payload do evento. `prompt` recebia; `script`
   rodava sem argumento e sem stdin. Um trigger de "post publicado" que não
   recebe o post não tem como saber o que distribuir.

Run:
    pytest tests/goals/test_trigger_ghost_entrypoint.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO_ROOT / "ADWs" / "routines" / "ghost_published_to_social.py"


def _rodar(entrada: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT)],
        input=entrada, capture_output=True, text=True, timeout=90, cwd=str(REPO_ROOT),
    )


# ── localização ──────────────────────────────────────────────────────────

def test_entrypoint_esta_onde_o_executor_permite():
    """O executor resolve WORKSPACE/ADWs/routines/<action_payload>."""
    assert ENTRYPOINT.is_file(), "trigger de script fora de ADWs/routines/ nunca roda"


def test_caminho_resolvido_pelo_executor_bate_com_o_arquivo():
    from_action_payload = REPO_ROOT / "ADWs" / "routines" / "ghost_published_to_social.py"
    assert from_action_payload.resolve() == ENTRYPOINT.resolve()


# ── payload por stdin ────────────────────────────────────────────────────

def test_executor_passa_o_evento_por_stdin():
    """Guarda a correção em routes/triggers.py — sem `input=` o script roda cego."""
    fonte = (REPO_ROOT / "dashboard" / "backend" / "routes" / "triggers.py").read_text(encoding="utf-8")
    trecho = fonte.split('elif trigger.action_type == "script"')[1].split("else:")[0]
    assert "input=" in trecho, "a ação script precisa receber o payload do evento"
    assert "event_data" in trecho, "o payload passado tem que ser o do evento"


def test_sem_payload_falha_em_vez_de_inventar_post():
    r = _rodar("")
    assert r.returncode == 1
    assert json.loads(r.stdout)["ok"] is False


def test_json_invalido_falha_de_forma_legivel():
    r = _rodar("{ isto não é json")
    assert r.returncode == 1
    assert "payload" in json.loads(r.stdout)["erro"]


def test_payload_que_nao_e_objeto_e_recusado():
    r = _rodar(json.dumps(["lista", "solta"]))
    assert r.returncode == 1


def test_payload_sem_id_de_post_diz_o_que_faltou():
    """Chega ao bridge e para lá — o erro tem que apontar o campo ausente."""
    r = _rodar(json.dumps({"post": {"current": {}}}))
    assert r.returncode == 1
    saida = json.loads(r.stdout)
    assert saida["ok"] is False
    assert "post.current.id" in saida["erro"]
