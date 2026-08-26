"""tests/backend/test_brain_repo_lock_orfao.py

2026-08-26 — o brain repo travava para sempre num `.git/index.lock` órfão.

Um único processo git interrompido (container derrubado no meio de um commit)
deixa `.git/index.lock` para trás. Todo `git add -A` seguinte sai com exit 128
e o sync **nunca mais roda**. Encontrado ao vivo: um lock de 22/08/2026, zero
bytes, manteve o versionamento do workspace parado por 4 dias. O único sinal
era um traceback repetido no log — ninguém associa isso a "meu workspace parou
de ser versionado".

O que este arquivo trava:
  1. lock antigo é removido e o `git add` é repetido — o sync se recupera
  2. lock RECENTE é respeitado: nunca disputar com um git legítimo em curso
  3. sem lock, nada muda (não inventa remoção onde não há problema)
  4. a falha que não é de lock continua subindo como antes

Run:
    pytest tests/backend/test_brain_repo_lock_orfao.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))

from brain_repo import git_ops  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    (d / ".git").mkdir(parents=True)
    return d


def _lock(repo: Path, idade_segundos: float) -> Path:
    p = repo / ".git" / "index.lock"
    p.write_text("")
    quando = time.time() - idade_segundos
    os.utime(p, (quando, quando))
    return p


# ── limpar_lock_orfao ────────────────────────────────────────────────────

def test_lock_antigo_e_removido(repo):
    lock = _lock(repo, idade_segundos=3600)
    assert git_ops.limpar_lock_orfao(repo) is True
    assert not lock.exists()


def test_lock_recente_e_respeitado(repo):
    """Nunca disputar com um git de fora que esteja legitimamente rodando."""
    lock = _lock(repo, idade_segundos=5)
    assert git_ops.limpar_lock_orfao(repo) is False
    assert lock.exists(), "removeu um lock que podia estar em uso"


def test_sem_lock_nao_faz_nada(repo):
    assert git_ops.limpar_lock_orfao(repo) is False


# ── integração com commit_all ────────────────────────────────────────────

def _resultado(returncode: int, stderr: str = "", stdout: str = ""):
    return subprocess.CompletedProcess(args=["git"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_commit_all_se_recupera_do_lock_orfao(repo):
    """O caso real: primeiro `git add` falha por lock, o lock é órfão, e a
    segunda tentativa passa — sem intervenção humana."""
    _lock(repo, idade_segundos=3600)
    erro_lock = _resultado(128, stderr="fatal: Unable to create '.git/index.lock': File exists.")
    chamadas = []

    def fake_run(cmd, cwd=None, timeout=None):
        chamadas.append(cmd)
        if cmd[:3] == ["git", "add", "-A"]:
            # falha só enquanto o lock existir
            if (repo / ".git" / "index.lock").exists():
                return erro_lock
            return _resultado(0)
        if cmd[:2] == ["git", "commit"]:
            return _resultado(0)
        return _resultado(0, stdout="x")  # git config --get

    with patch.object(git_ops, "_run", side_effect=fake_run):
        assert git_ops.commit_all(repo, "mensagem") is True

    adds = [c for c in chamadas if c[:3] == ["git", "add", "-A"]]
    assert len(adds) == 2, "não repetiu o add depois de limpar o lock"


def test_commit_all_nao_remove_lock_recente(repo):
    """Lock novo: o erro sobe, e o arquivo continua lá."""
    lock = _lock(repo, idade_segundos=5)
    erro_lock = _resultado(128, stderr="fatal: Unable to create '.git/index.lock': File exists.")

    def fake_run(cmd, cwd=None, timeout=None):
        if cmd[:3] == ["git", "add", "-A"]:
            return erro_lock
        return _resultado(0, stdout="x")

    with patch.object(git_ops, "_run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="git add -A failed"):
            git_ops.commit_all(repo, "mensagem")
    assert lock.exists()


def test_falha_que_nao_e_de_lock_continua_subindo(repo):
    """Não engolir erro diferente só porque agora existe um caminho de retry."""
    def fake_run(cmd, cwd=None, timeout=None):
        if cmd[:3] == ["git", "add", "-A"]:
            return _resultado(128, stderr="fatal: not a git repository")
        return _resultado(0, stdout="x")

    with patch.object(git_ops, "_run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="not a git repository"):
            git_ops.commit_all(repo, "mensagem")
