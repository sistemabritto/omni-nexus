"""Registro de rotinas — a fonte única do que roda, quando, e a que custo.

Antes disto a página de Rotinas era montada por três caminhos que não
conversavam, e cada um mentia de um jeito:

1. `/api/scheduler` lia `scheduler.py` **com regex sobre o código-fonte**. O
   regex não distingue uma rotina agendada de uma linha do próprio carregador
   de YAML, então a tela mostrava uma rotina fantasma chamada `""` que rodava
   "every interval_min min" — um trecho de código lido como se fosse dado.
2. `/api/routines` inventava um id abreviado (`good_morning` → `morning`) que
   NÃO é o id com que o runner grava as métricas (`good-morning`). Resultado: a
   mesma rotina aparecia duas vezes, uma com 25 execuções e outra zerada. Metade
   da tela era esse fantasma.
3. Os totais somavam `val["cost"]` e `val["tokens"]`, chaves que não existem —
   as reais são `total_cost_usd` e `total_input_tokens`/`total_output_tokens`.
   O painel exibia custo total R$ 0,00 com US$ 27 gastos no arquivo.

Aqui a lista sai do agendador de verdade (`schedule.get_jobs()` depois de
`setup_schedule()`), não de texto, e cada rotina carrega o motor que a move —
que é a pergunta cara: quais gastam token e quais são Python determinístico.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from routes._helpers import WORKSPACE, safe_read

# ── motor: Python puro ou modelo de linguagem ────────────────────────────

# Marcas de que o código chama um modelo. Custam dinheiro por execução; o resto
# custa só CPU. É a distinção que decide se vale agendar de 15 em 15 minutos.
#
# São CHAMADAS, nunca o import do módulo. `from runner import ...` marcava o
# backup diário como rotina de modelo — ele importa `run_script`, que é o
# executor de função Python e não fala com modelo nenhum. Vinte e sete
# execuções e US$ 0,00 no histórico confirmavam; a heurística é que estava
# errada. Aqui vale `run_claude(` e `run_skill(`, que são os que gastam.
_MARCAS_DE_MODELO = re.compile(
    r"XAI_API_KEY|api\.x\.ai|ANTHROPIC_API_KEY|api\.anthropic\.com|OPENAI_API_KEY"
    r"|omniroute|OMNIROUTE|run_claude\s*\(|run_skill\s*\(|claude_code|openclaude"
    r"|_pedir_ao_modelo|chat/completions|/v1/responses",
    re.I)

# Um script raramente chama o modelo em si — ele importa quem chama. Seguir os
# imports locais um nível resolve o caso real: `derivar_redes_pendentes.py` é
# quatro linhas de entrypoint, e quem gasta token é o `ghost_social_bridge` que
# ele importa. Parar no arquivo de entrada classificaria a rotina mais cara
# como "Python puro".
_PROFUNDIDADE = 1


def _fontes_locais(texto: str) -> list[Path]:
    """Módulos do próprio workspace que este código importa."""
    nomes = set(re.findall(r"^\s*(?:from|import)\s+([a-z_][a-z0-9_]*)", texto, re.M))
    achados = []
    for nome in nomes:
        for base in (WORKSPACE / "dashboard" / "backend", WORKSPACE / "ADWs" / "routines"):
            caminho = base / f"{nome}.py"
            if caminho.is_file():
                achados.append(caminho)
    return achados


def motor_do_script(script: str) -> str:
    """"modelo" se a rotina chama uma LLM, "python" se é determinística.

    Vazio quando o arquivo não existe — melhor não afirmar do que chutar.
    """
    if not script:
        return ""
    # Os mesmos três candidatos que `scheduler.run_adw` resolve — uma rotina
    # não precisa mudar de lugar só para ser agendada, e `publish_scheduled.py`
    # mora em `scripts/`. Procurar só em ADWs/routines devolvia "" justamente
    # para a rotina que roda a cada 15 minutos.
    for base in (WORKSPACE / "ADWs" / "routines",
                 WORKSPACE / "ADWs" / "routines" / "custom",
                 WORKSPACE / "scripts"):
        caminho = base / script.replace("custom/", "")
        if caminho.is_file():
            break
    else:
        return ""

    vistos: set[Path] = set()
    fila = [(caminho, 0)]
    while fila:
        atual, nivel = fila.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        texto = safe_read(atual) or ""
        if _MARCAS_DE_MODELO.search(texto):
            return "modelo"
        if nivel < _PROFUNDIDADE:
            fila.extend((f, nivel + 1) for f in _fontes_locais(texto))
    return "python"


# ── agendamento real ─────────────────────────────────────────────────────

# Lê o agendador num processo à parte. Importar `scheduler` dentro do Flask
# registraria os jobs no `schedule` global do dashboard — que ninguém executa,
# mas que passaria a existir no processo errado. Um subprocess isola isso e
# ainda protege a página caso `scheduler.py` esteja quebrado.
_LEITOR = r"""
import json, sys
sys.path.insert(0, %(workspace)r)
import scheduler, schedule
scheduler.setup_schedule()
saida = []
for j in schedule.get_jobs():
    args = list(getattr(j.job_func, "args", ()) or ())
    nome = args[0] if args else getattr(j.job_func, "__name__", "")
    script = args[1] if len(args) > 1 else ""
    saida.append({
        "name": str(nome),
        "script": str(script),
        "interval": j.interval,
        "unit": j.unit,
        "at_time": str(j.at_time) if j.at_time else "",
        "start_day": j.start_day or "",
        "next_run": j.next_run.isoformat() if j.next_run else "",
    })
print(json.dumps(saida))
"""

# Rotinas registradas por um wrapper em vez de `run_adw` direto — o agendador
# só enxerga o nome da função Python. Sem isto a tela mostra
# "_hourly_report_safe", que não diz a ninguém o que a rotina faz.
_WRAPPERS = {
    "_hourly_report_safe": ("Relatório de Hora em Hora", "hourly_report.py"),
}

_CACHE: dict = {"quando": 0.0, "dados": None}
_VALIDADE_S = 60


def agendamento_real(forcar: bool = False) -> list[dict] | None:
    """O que o agendador registrou de fato. `None` se não foi possível ler.

    Cache de 60s porque cada leitura custa um interpretador subindo, e o
    agendamento só muda em deploy — não faz sentido pagar isso a cada F5.
    """
    agora = time.time()
    if not forcar and _CACHE["dados"] is not None and agora - _CACHE["quando"] < _VALIDADE_S:
        return _CACHE["dados"]
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _LEITOR % {"workspace": str(WORKSPACE)}],
            capture_output=True, text=True, timeout=60, cwd=str(WORKSPACE))
        if proc.returncode != 0:
            print(f"[routines_registry] agendador não pôde ser lido: {proc.stderr[-300:]}",
                  flush=True)
            return None
        dados = json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001 — a página não pode cair com o agendador
        print(f"[routines_registry] falha ao ler o agendador: {exc}", flush=True)
        return None
    for job in dados:
        nome, script = _WRAPPERS.get(job.get("name") or "", ("", ""))
        if nome:
            job["name"], job["script"] = nome, script
    _CACHE.update({"quando": agora, "dados": dados})
    return dados


def descrever_frequencia(job: dict) -> tuple[str, str]:
    """(rótulo legível em pt-BR, bucket de ordenação)."""
    unidade = (job.get("unit") or "").rstrip("s")
    intervalo = job.get("interval") or 1
    hora = job.get("at_time") or ""
    hora = hora[:5] if re.match(r"^\d{2}:\d{2}", hora) else hora
    dia = (job.get("start_day") or "").lower()

    dias_pt = {"monday": "Segunda", "tuesday": "Terça", "wednesday": "Quarta",
               "thursday": "Quinta", "friday": "Sexta", "saturday": "Sábado",
               "sunday": "Domingo"}
    if dia:
        return (f"{dias_pt.get(dia, dia.capitalize())} às {hora}" if hora
                else dias_pt.get(dia, dia.capitalize())), "semanal"
    if unidade == "minute":
        return (f"A cada {intervalo} min" if intervalo != 1 else "A cada minuto"), "intervalo"
    if unidade == "hour":
        return (f"A cada {intervalo}h" if intervalo != 1 else "De hora em hora"), "intervalo"
    if unidade == "day":
        return (f"Todo dia às {hora}" if hora else "Todo dia"), "diaria"
    if unidade == "week":
        return (f"Toda semana às {hora}" if hora else "Toda semana"), "semanal"
    return (unidade or "?"), "outro"
