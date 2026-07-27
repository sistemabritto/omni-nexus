"""Reduz a capa antes de ela subir para o Ghost.

O gerador de thumbnail devolve PNG. PNG é formato para gráfico com área
chapada, não para fotografia: a capa de 1536×1024 saía com 2,3 MB, e mesmo a
variante de 750px que o Ghost gera sozinho ficava em 665 KB. Três dessas na
home do blog somam 2 MB só de imagem — o Lighthouse apontou 2.532 KiB de
desperdício e a performance caiu de 83 para 78 quando o tema novo entrou.

A conversão em si mora em `otimizar_imagem.js`, porque quem faz isso bem é o
sharp e não há Pillow nos containers. Este módulo é só a ponte.

**Fail-open de propósito**: qualquer erro devolve o arquivo original. Uma capa
pesada é um problema de performance; nenhuma capa é um artigo sem imagem no
Telegram, no blog e nas redes.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

SCRIPT = Path(__file__).resolve().parent / "otimizar_imagem.js"

# 1600px cobre a maior variante que o tema pede (xl = 2000, mas a capa nasce
# com 1536). Acima do original não há ganho — só peso.
LARGURA_ALVO = 1600
QUALIDADE = 82   # onde o artefato ainda não aparece em foto


def otimizar(origem: Path, *, largura: int = LARGURA_ALVO,
             qualidade: int = QUALIDADE) -> tuple[Path, dict]:
    """Converte para WebP redimensionando. Devolve (caminho, relatório).

    O caminho devolvido é o do WebP quando dá certo, e o da origem quando não
    dá — então quem chama nunca precisa tratar o caso de falha.
    """
    origem = Path(origem)
    if not origem.is_file():
        return origem, {"ok": False, "erro": "arquivo inexistente"}

    destino = origem.with_suffix(".webp")
    if not shutil.which("node"):
        log.warning("node ausente; a capa sobe no formato original")
        return origem, {"ok": False, "erro": "node ausente"}

    try:
        proc = subprocess.run(
            ["node", str(SCRIPT), str(origem), str(destino), str(largura), str(qualidade)],
            capture_output=True, text=True, timeout=120,
        )
        relatorio = json.loads((proc.stdout or "{}").strip() or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        log.warning("otimização de imagem falhou (%s); segue o original", exc)
        return origem, {"ok": False, "erro": str(exc)}

    if not relatorio.get("ok") or not destino.is_file():
        log.warning("otimização não produziu arquivo: %s", relatorio.get("erro"))
        return origem, relatorio

    log.info("capa otimizada: %s KB -> %s KB (-%s%%)",
             relatorio["antes"] // 1024, relatorio["depois"] // 1024,
             relatorio.get("reducao_pct", 0))
    return destino, relatorio
