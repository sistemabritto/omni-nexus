#!/usr/bin/env python3
"""ADW: Good Morning — briefing matinal. Dados em Python, leitura pelo modelo.

Antes esta rotina era uma linha: `run_skill("prod-good-morning")`. A skill,
porém, foi escrita para conversa e não para cron — ela manda o agente ler
CLAUDE.md, os três últimos logs, o overview de cada projeto ativo, consultar
três integrações, montar um HTML e **perguntar ao usuário se ele quer entrar
num projeto**. Às 07:00 não há ninguém para responder. Daí os dois números que
o painel passou a mostrar: US$ 0,16 por execução e 76% de acerto.

A divisão agora é por natureza do trabalho:

- **Python** coleta o que é consulta: Todoist, aprovações pendentes, tickets
  abertos, rotinas que falharam, pauta do dia. Custa zero e não erra.
- **O modelo** recebe isso pronto e faz o que só ele faz: olhar o conjunto,
  cruzar com a agenda e os e-mails (que só existem via MCP) e dizer no que
  prestar atenção hoje.

Se a coleta falhar, a skill roda mesmo assim, do jeito antigo. Um briefing sem
o dossiê ainda é um briefing; nenhum briefing é uma manhã às cegas.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "dashboard", "backend"))

from runner import banner, run_skill, summary  # noqa: E402


def coletar_dossie() -> str:
    try:
        from briefing_dados import em_markdown

        return em_markdown()
    except Exception as exc:  # noqa: BLE001
        print(f"[good_morning] coleta falhou, seguindo sem dossiê: {exc}", flush=True)
        return ""


def main():
    banner("☀️  Good Morning", "Dossiê em Python • leitura por @clawdia")

    dossie = coletar_dossie()
    # O dossiê vai como argumento da skill. A skill sabe que, quando ele chega,
    # não deve sair procurando os mesmos dados de novo — é essa instrução que
    # corta os turnos de navegação.
    args = f"--dossie-pronto\n\n{dossie}" if dossie else ""

    results = [run_skill("prod-good-morning", args=args, log_name="good-morning",
                         timeout=600, agent="clawdia-assistant", notify_telegram=True)]
    summary(results, "Good Morning")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠ Cancelado.")
