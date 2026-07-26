#!/usr/bin/env python3
"""Esteira diária de conteúdo — consome a fila de pautas e abre os gates.

O elo que faltava entre o research semanal e a publicação. O ciclo completo:

    domingo   weekly_content_research  → 21 pautas na fila (status: proposta)
    humano    aprova o ciclo em lote   → status: aprovada
    diário    ESTA ROTINA              → escreve, cria draft, gera capa,
                                         abre o gate do artigo (status: escrita)
    humano    aprova o artigo          → publica no Ghost (status: publicada)
    automático                         → deriva X/LinkedIn/Threads, um gate cada

Nada aqui publica. A rotina produz o rascunho e para no gate — o humano
continua sendo quem decide o que vai ao ar, que é a razão de o fluxo inteiro
existir.

Fail-closed por pauta: uma que falha não derruba as outras duas do dia. O
relatório diz exatamente qual falhou e por quê, em vez de sumir em silêncio.

Uso:
    python ADWs/routines/daily_content_pipeline.py             # o dia de hoje
    python ADWs/routines/daily_content_pipeline.py --dia 2026-07-28
    python ADWs/routines/daily_content_pipeline.py --limite 1  # só a primeira
    python ADWs/routines/daily_content_pipeline.py --dry-run   # não toca em nada
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard" / "backend"))


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def gerar_capa(post: dict, titulo: str) -> tuple[str, str]:
    """Thumbnail com o rosto do Felipe. Devolve (url, erro).

    Usa o banco de rostos real — a referência errada já foi ao ar uma vez com
    a cara de outra pessoa, e o primer foi corrigido justamente por isso.
    """
    from ghost_publisher import briefing_de_capa, subir_imagem
    from thumbnail_maker import gerar, montar_prompt

    brief = briefing_de_capa({**post, "title": titulo})
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "capa.png"
        erro = gerar(montar_prompt(brief["headline"], brief["hook"],
                                   brief["expressao"], brief["badge"]), destino)
        if erro:
            return "", erro
        return subir_imagem(destino)


def processar(pauta: dict, dry_run: bool) -> dict:
    """Uma pauta: escreve, cria o rascunho, gera a capa, abre o gate."""
    import pauta_fila
    from escritor_de_artigo import escrever
    from ghost_publisher import atualizar, buscar, criar_rascunho
    from ghost_social_bridge import aprovar_artigo

    rotulo = f"#{pauta['prioridade']} {pauta['keyword']!r}"
    log(f"{rotulo} — escrevendo")

    artigo, erro = escrever(pauta)
    if erro:
        return {"pauta": pauta["id"], "ok": False, "etapa": "escrita", "erro": erro}
    log(f"{rotulo} — {artigo['palavras']} palavras: {artigo['titulo'][:60]}")

    if dry_run:
        return {"pauta": pauta["id"], "ok": True, "dry_run": True,
                "titulo": artigo["titulo"], "palavras": artigo["palavras"]}

    post_id, erro = criar_rascunho(artigo["titulo"], artigo["html"],
                                   excerpt=artigo["excerpt"])
    if erro:
        return {"pauta": pauta["id"], "ok": False, "etapa": "rascunho", "erro": erro}

    # A pauta vira `escrita` assim que o rascunho existe, ANTES da capa e do
    # gate. Se a capa falhar, o trabalho de escrita não se perde e uma nova
    # execução não reescreve o artigo do zero.
    pauta_fila.mover(pauta["id"], "escrita", ghost_post_id=post_id, titulo=artigo["titulo"])

    aviso_capa = ""
    url_capa, erro_capa = gerar_capa(buscar(post_id) or {}, artigo["titulo"])
    if erro_capa:
        aviso_capa = f"capa falhou: {erro_capa}"
        log(f"{rotulo} — {aviso_capa}")
    else:
        atualizar(post_id, feature_image=url_capa)

    gate = aprovar_artigo(post_id, publicar_em=pauta["publish_at"])
    if not gate.get("ok") or gate.get("ignorado"):
        return {"pauta": pauta["id"], "ok": False, "etapa": "gate",
                "erro": gate.get("erro") or gate.get("ignorado"), "post_id": post_id}

    return {"pauta": pauta["id"], "ok": True, "post_id": post_id,
            "titulo": artigo["titulo"], "palavras": artigo["palavras"],
            "publish_at": pauta["publish_at"], "ticket": gate.get("ticket"),
            "aviso": aviso_capa or None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", help="dia a processar (default: hoje)")
    ap.add_argument("--limite", type=int, default=0, help="processa no máximo N pautas")
    ap.add_argument("--dry-run", action="store_true", help="escreve mas não cria nada")
    args = ap.parse_args()

    load_env()
    import pauta_fila

    dia = date.fromisoformat(args.dia) if args.dia else date.today()

    # Limpa a fila antes de olhar o dia: pauta que passou da data carrega
    # gancho de notícia morto, e escrever a partir dela publica assunto velho.
    if not args.dry_run:
        vencidas = pauta_fila.vencer_atrasadas()
        if vencidas:
            log(f"{vencidas} pauta(s) vencida(s) descartada(s)")

    pautas = pauta_fila.do_dia(dia, status="aprovada")
    if args.limite:
        pautas = pautas[: args.limite]
    if not pautas:
        log(f"nenhuma pauta aprovada para {dia} — nada a fazer")
        return 0

    log(f"{len(pautas)} pauta(s) aprovada(s) para {dia}")
    resultados = [processar(p, args.dry_run) for p in pautas]

    ok = [r for r in resultados if r["ok"]]
    falhas = [r for r in resultados if not r["ok"]]
    log(f"fim — {len(ok)} rascunho(s) no gate, {len(falhas)} falha(s)")
    for f in falhas:
        log(f"  falhou na {f['etapa']}: {f['erro']}")

    # Só o que falhou vira alerta. Sucesso já aparece como gate no Telegram —
    # avisar duas vezes a mesma coisa é ruído que ensina a ignorar o canal.
    if falhas and not args.dry_run:
        try:
            from notifications import send_telegram_alert

            send_telegram_alert(
                f"⚠️ <b>Esteira de conteúdo {dia}</b>\n"
                f"{len(ok)} no gate, {len(falhas)} falharam:\n"
                + "\n".join(f"• {f['etapa']}: {f['erro'][:120]}" for f in falhas))
        except Exception as exc:  # noqa: BLE001 — alerta não pode derrubar a rotina
            log(f"não consegui alertar no Telegram: {exc}")

    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
