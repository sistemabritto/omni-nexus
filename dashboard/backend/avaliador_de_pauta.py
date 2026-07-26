"""Julga se uma keyword vira pauta boa para a Sistema Britto.

O filtro por regex separa lixo óbvio — curso técnico, vaga de emprego, caixa
de plástico — mas não julga público. Ele deixava passar `mercado pago api`
(assunto de outro negócio) e `como postar story no instagram pelo pc`
(consumidor final, não dono de empresa), porque as duas contêm termos do
domínio e intenção comercial.

Julgar público exige entender o negócio, e é o que este módulo faz: manda as
candidatas em lote com o perfil real da Sistema Britto e recebe nota de 0 a 10.
Roda uma vez por semana, sobre ~100 candidatas, numa única chamada — barato
para o que evita, que é gastar um dos 21 slots da semana com pauta que não
converte.

O perfil vem do site (sistemabritto.com.br, lido em 2026-07-26), não da minha
impressão sobre o negócio.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

# O que a Sistema Britto vende, em quais palavras. Serve de régua para o
# julgamento: pauta boa é a que um comprador destes produtos buscaria antes de
# comprar — não a que qualquer pessoa buscaria sobre o mesmo assunto.
PERFIL = """A Sistema Britto vende força de trabalho de IA que opera funções do
negócio sozinha. Três ofertas:

1. WhatsApp com IA (R$ 297/mês) — a IA qualifica lead, agenda, vende e reativa
   base parada, 24h. Promessa: "seu concorrente responde em 1 segundo, você em
   1 hora". Para quem vende por WhatsApp: clínica, estúdio, delivery, prestador
   de serviço, time comercial. Funil: sistemabritto.com.br/whatsapp

2. SocialJobs — conteúdo diário em cinco redes (YouTube, TikTok, Instagram,
   LinkedIn, X) produzido por agentes especialistas, com calendário automático.
   Para quem precisa de presença constante e não consegue manter ritmo.
   Funil: sistemabritto.com.br/socialjobs

3. Sob medida — SaaS, e-commerce, assistente de IA e funil no domínio e na
   marca do cliente, no ar em 48h. Funil: sistemabritto.com.br/sistema

QUEM COMPRA: dono de negócio (digital ou local) que já vende e trava na
operação — perde lead por demora, não mantém constância de conteúdo, ou faz na
mão o que deveria ser automático. NÃO é desenvolvedor, NÃO é estudante, NÃO é
quem procura emprego, NÃO é consumidor final curioso."""

CRITERIOS = """Dê nota de 0 a 10 para cada keyword, medindo UMA coisa: a
probabilidade de quem digitou isso no Google virar cliente de uma das três
ofertas.

10 — quem busca isso está avaliando comprar exatamente o que vendemos.
      ex: "chatbot whatsapp para empresas", "automatizar atendimento whatsapp"
 7 — dono de negócio com a dor que resolvemos, ainda pesquisando.
      ex: "melhor horário para postar no instagram", "como gerar mais leads"
 4 — tangencia o assunto, mas o público provável é outro.
      ex: "como postar story pelo pc" (consumidor final)
 0 — assunto de outro negócio, estudante, candidato a vaga ou curioso.
      ex: "mercado pago api", "curso de marketing digital", "salário de analista"

Penalize sem dó: keyword de consumidor final que só parece comercial, assunto
de produto de terceiro que não integramos, e busca informativa sem intenção de
resolver um problema de operação."""

# Abaixo disto a pauta não entra na semana. 6 deixa passar "dono de negócio
# pesquisando" e barra "consumidor final curioso", que é exatamente a linha
# que o regex não conseguia enxergar.
NOTA_MINIMA = 6


def _montar_prompt(keywords: list[str]) -> str:
    listadas = "\n".join(f"{i}. {kw}" for i, kw in enumerate(keywords, 1))
    return (
        f"{PERFIL}\n\n{CRITERIOS}\n\n"
        f"KEYWORDS:\n{listadas}\n\n"
        "Responda APENAS um JSON no formato "
        '{"notas": [{"n": <número da lista>, "nota": <0-10>, "porque": "<até 8 palavras>"}]}. '
        "Uma entrada por keyword, na ordem. Sem texto antes ou depois."
    )


def _extrair(bruto: str) -> list[dict]:
    limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", (bruto or "").strip())
    try:
        return json.loads(limpo).get("notas") or []
    except (json.JSONDecodeError, ValueError, AttributeError):
        m = re.search(r"\{.*\}", limpo, re.S)
        if not m:
            return []
        try:
            return json.loads(m.group(0)).get("notas") or []
        except (json.JSONDecodeError, ValueError, AttributeError):
            return []


# Lote grande demais faz o modelo encurtar a lista e devolver menos notas que
# keywords; pequeno demais multiplica chamadas. 40 é o meio-termo testado.
POR_LOTE = 40


def avaliar(candidatas: list[dict], *, nota_minima: int = NOTA_MINIMA) -> list[dict]:
    """Ordena as candidatas por relevância para o ICP e corta as fracas.

    Cada item ganha `nota` e `porque`. Fail-open de propósito: se o modelo não
    responder, devolve a lista original intacta. Perder a semana inteira porque
    um julgamento opcional falhou seria pior que publicar uma pauta mediana.
    """
    if not candidatas:
        return []

    from ghost_publisher import _pedir_ao_modelo

    notas: dict[str, dict] = {}
    for inicio in range(0, len(candidatas), POR_LOTE):
        lote = candidatas[inicio:inicio + POR_LOTE]
        bruto = _pedir_ao_modelo(_montar_prompt([c["kw"] for c in lote]), timeout=300)
        for item in _extrair(bruto):
            try:
                indice = int(item["n"]) - 1
                nota = float(item["nota"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= indice < len(lote):
                notas[lote[indice]["kw"]] = {"nota": nota,
                                             "porque": str(item.get("porque") or "")[:80]}

    if not notas:
        log.warning("avaliador não devolveu nota nenhuma — seguindo com o filtro por regex")
        return candidatas

    julgadas = []
    for c in candidatas:
        veredito = notas.get(c["kw"])
        if veredito is None:
            # Sem nota não é sinal de nota baixa: pode ter sido lote perdido.
            # Entra com a nota de corte para não sumir por omissão do modelo.
            julgadas.append({**c, "nota": float(nota_minima), "porque": "não avaliada"})
            continue
        if veredito["nota"] >= nota_minima:
            julgadas.append({**c, **veredito})

    cortadas = len(candidatas) - len(julgadas)
    if cortadas:
        log.info("avaliador cortou %d de %d por baixa relevância", cortadas, len(candidatas))
    # Relevância primeiro, retorno de SEO como desempate: uma pauta nota 9 com
    # 200 buscas vale mais que uma nota 6 com 2000, porque a segunda traz
    # visita que não compra.
    julgadas.sort(key=lambda c: (-c["nota"], -(c.get("vol") or 0) / (1 + (c.get("kd") or 0))))
    return julgadas
