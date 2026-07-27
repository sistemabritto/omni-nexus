"""Escreve o artigo a partir de uma pauta da fila.

A ponte que faltava. O research levantava a pauta e o gate sabia publicar o
artigo, mas ninguém escrevia o artigo — o meio do caminho era manual, e por
isso a esteira parava todo dia.

Duas regras que vieram de correções do Felipe e viraram parte do prompt, não
sugestão:

- O humanizer é obrigatório. "É importante que todo blog post seja escrito
  usando a Skill Humanizer" — o guia entra no prompt de escrita, não só na
  revisão depois que ele reclama do tom.
- Todo artigo aponta para um funil real (/whatsapp, /socialjobs, /sistema).
  Artigo que informa e não converte é tráfego doado.

E uma que vem do formato: GEO. A pergunta do título é respondida nos dois
primeiros parágrafos, cada H2 abre com resposta curta, e todo número carrega
a fonte. É o que faz a LLM citar o artigo em vez de só indexá-lo.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
HUMANIZER = WORKSPACE / ".claude" / "skills" / "mkt-quality-gate" / "experts" / "humanizer.md"

FUNIS = {
    "whatsapp": ("https://sistemabritto.com.br/whatsapp",
                 "automação de atendimento e vendas no WhatsApp"),
    "socialjobs": ("https://sistemabritto.com.br/socialjobs",
                   "produção de conteúdo e presença nas redes"),
    # Reposicionado em 27/07/2026: a página não vende mais "solução web sob
    # encomenda", vende a call de 1h que produz o PRD do projeto. O CTA do
    # artigo precisa prometer o que a página entrega — senão o leitor clica
    # esperando uma coisa e encontra outra, que é a forma mais cara de perder
    # alguém que já estava interessado.
    "sistema": ("https://sistemabritto.com.br/sistema",
                "a call de 1h que define seu projeto inteiro — escopo, prazo e "
                "preço no mesmo documento"),
}


def funil_de(keyword: str) -> str:
    """Slug do funil a que uma pauta pertence.

    Regra simples e explícita em vez de deixar o modelo escolher: ele inventaria
    um CTA genérico, e CTA genérico não converte. Na dúvida vai para /sistema,
    que é o guarda-chuva.

    Pública porque o research semanal também precisa dela — é assim que ele
    equilibra a semana entre os três funis em vez de deixar o WhatsApp, que tem
    volume de busca muito maior, levar todos os 21 slots.
    """
    texto = keyword.lower()
    # "lead" ficou de fora de propósito: é vocabulário dos três funis, e
    # mandava "gerar leads com inteligência artificial" — seed do /sistema —
    # para o CTA do WhatsApp.
    if any(t in texto for t in ("whatsapp", "atendimento", "chatbot", "disparo")):
        return "whatsapp"
    if any(t in texto for t in ("instagram", "tiktok", "youtube", "post", "conteúdo",
                                "conteudo", "rede social", "redes sociais", "seguidor",
                                "reels", "shorts", "stories", "story", "carrossel",
                                "editorial", "engajamento")):
        return "socialjobs"
    return "sistema"


def _funil_para(keyword: str) -> tuple[str, str]:
    """URL e descrição do funil da pauta."""
    return FUNIS[funil_de(keyword)]


def _briefing_humanizer() -> str:
    if HUMANIZER.is_file():
        return HUMANIZER.read_text(encoding="utf-8", errors="replace")[:6000]
    log.warning("humanizer.md não encontrado em %s — artigo sai sem o guia", HUMANIZER)
    return ""


def montar_prompt(pauta: dict, noticia: str = "") -> str:
    from datetime import date

    keyword = pauta["keyword"]
    funil_url, funil_desc = _funil_para(keyword)
    hoje = date.today()
    return (
        "Você escreve um artigo de blog em português do Brasil para a Sistema Britto, "
        "que vende automação e operação com IA para donos de empresa. Devolva um JSON "
        "com as chaves titulo, excerpt e html — nada além do JSON.\n\n"

        # A data vai explícita porque o corte de treino do modelo é anterior a
        # ela: o primeiro artigo real saiu intitulado "…em 2025" enquanto o
        # blog publicava em 2026. Ano errado no título envelhece o post no dia
        # em que ele nasce.
        f"HOJE É {hoje:%d/%m/%Y}. O ano corrente é {hoje.year} — se citar ano, "
        f"é este, nunca um anterior.\n\n"
        f"PALAVRA-CHAVE PRINCIPAL: {keyword}\n"
        + (f"VOLUME DE BUSCA: {pauta.get('volume')} / mês (dificuldade {pauta.get('kd')})\n"
           if pauta.get("volume") else "")
        + (f"\nGANCHO DE NOTÍCIA DESTA SEMANA (use se couber, com a fonte):\n{noticia[:1500]}\n"
           if noticia else "")
        + "\n"

        "FORMATO (GEO — é o que faz a LLM citar o artigo, não só indexar):\n"
        "- O título é uma pergunta ou promessa concreta e contém a palavra-chave.\n"
        "- Os DOIS primeiros parágrafos respondem a pergunta do título. Sem rodeio, "
        "sem 'neste artigo você vai descobrir'.\n"
        "- Cada <h2> é uma pergunta, e o parágrafo logo abaixo dá a resposta curta "
        "antes de desenvolver.\n"
        "- Todo número tem fonte com <a href> para a origem. Sem fonte, não use o número.\n"
        "- 1200 a 1600 palavras. HTML limpo: <p>, <h2>, <h3>, <ul>, <a>, <strong>.\n"
        "- Sem <html>, <head>, <body>, sem cerca de código.\n\n"

        f"CTA OBRIGATÓRIO no último parágrafo, apontando para {funil_url} "
        f"({funil_desc}). Um só, específico, ligado ao que o artigo acabou de ensinar.\n\n"

        "MARCA:\n"
        "- Tom direto, de quem construiu. Nunca de quem vende.\n"
        "- PROIBIDO: 'juntos vamos', 'revolucionar', 'transformação digital', "
        "'disruptivo', 'garanta já', 'últimas vagas', promessa de resultado sem dado.\n"
        "- Nunca invente número, data, caso de cliente ou métrica.\n\n"

        f"GUIA ANTI-ESCRITA-DE-IA (obrigatório, não é sugestão):\n{_briefing_humanizer()}"
    )


def _extrair_json(bruto: str) -> dict:
    """JSON do modelo, tolerando cerca de código e texto em volta."""
    import json

    limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", (bruto or "").strip())
    try:
        return json.loads(limpo)
    except (json.JSONDecodeError, ValueError):
        pass
    # Último recurso: o maior bloco entre chaves.
    m = re.search(r"\{.*\}", limpo, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


# Abaixo disto não é artigo, é resumo. Publicar um texto de 300 palavras como
# se fosse o post da pauta gasta o slot da semana com nada.
MINIMO_DE_PALAVRAS = 600


def escrever(pauta: dict, *, noticia: str = "") -> tuple[dict, str]:
    """Gera o artigo da pauta. Devolve (artigo, erro).

    `artigo` traz titulo, excerpt e html. Fail-closed: texto curto demais ou
    sem CTA de funil não é devolvido como sucesso — melhor a rotina registrar
    a falha e o slot ficar vazio do que publicar um artigo pela metade.
    """
    from ghost_publisher import _pedir_ao_modelo

    bruto = _pedir_ao_modelo(montar_prompt(pauta, noticia), timeout=420)
    if not bruto:
        return {}, "modelo não respondeu (XAI_API_KEY ausente ou chamada falhou)"

    artigo = _extrair_json(bruto)
    titulo = (artigo.get("titulo") or "").strip()
    html = (artigo.get("html") or "").strip()
    if not titulo or not html:
        return {}, "resposta do modelo sem titulo ou html utilizável"

    palavras = len(re.sub(r"<[^>]+>", " ", html).split())
    if palavras < MINIMO_DE_PALAVRAS:
        return {}, f"artigo curto demais ({palavras} palavras, mínimo {MINIMO_DE_PALAVRAS})"

    funil_url, _ = _funil_para(pauta["keyword"])
    if funil_url not in html:
        # Preferimos anexar a recusar: o texto está bom, só faltou o CTA, e
        # perder o artigo inteiro por causa de um link seria desperdício.
        html += (f'\n<p>Se você quer isso funcionando na sua operação sem montar tudo '
                 f'do zero, <a href="{funil_url}">veja como a gente faz</a>.</p>')
        log.info("CTA de funil ausente no artigo '%s' — anexado ao final", titulo[:60])

    # Marca a origem no link do funil. Sem isto o clique chega ao site como
    # "direct" e não há como saber que veio do blog — em 30 dias, 134 de 141
    # visitas caíram nesse balde cego.
    from utm import marcar_no_texto

    html = marcar_no_texto(html, "blog", campanha=titulo)

    return {
        "titulo": titulo,
        "excerpt": (artigo.get("excerpt") or "").strip()[:300],
        "html": html,
        "palavras": palavras,
    }, ""
