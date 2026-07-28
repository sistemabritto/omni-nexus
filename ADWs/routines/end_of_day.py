#!/usr/bin/env python3
"""ADW: End of Day — consolidação do dia. Dados em Python, síntese pelo modelo.

Mesma divisão do briefing matinal, pelo mesmo motivo. A skill
`prod-end-of-day` manda coletar seis fontes antes de pensar: memória dos
agentes, logs de rotina, reuniões, Todoist, git e a conversa da sessão. Cinco
delas são consulta pura, e a sexta (a conversa da sessão) nem existe quando
quem chama é o cron das 21:00.

Coletar aquilo com ferramenta, um turno por fonte, era o que fazia esta rotina
custar US$ 7,84 acumulados — a mais cara do workspace depois que a esteira AI
News saiu.

O que sobra para o modelo é o que ele faz bem e o Python não faz: ler o dia
inteiro de uma vez, decidir o que ali é aprendizado e escrever a memória.
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
        from briefing_dados import fim_do_dia_em_markdown

        return fim_do_dia_em_markdown()
    except Exception as exc:  # noqa: BLE001
        print(f"[end_of_day] coleta falhou, seguindo sem dossiê: {exc}", flush=True)
        return ""


def main():
    banner("🌙 End of Day", "Dossiê em Python • síntese por @clawdia")

    dossie = coletar_dossie()
    args = f"--dossie-pronto\n\n{dossie}" if dossie else ""

    results = [run_skill("prod-end-of-day", args=args, log_name="end-of-day",
                         timeout=600, agent="clawdia-assistant", notify_telegram=True)]
    summary(results, "End of Day")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠ Cancelado.")
