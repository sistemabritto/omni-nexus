"""Convenção de UTM — a origem de cada clique que a esteira gera.

Sem isto o site não sabe de onde vem o tráfego. Medido em 26/07/2026 no
analytics de sistemabritto.com.br: de 141 visitas em 30 dias, **134 caíram em
"direct"** — ou seja, 95% sem origem identificável. Das 7 restantes, duas
grafias diferentes apontavam para a mesma rede (`ig` com 4 e `instagram` com
2), o que fragmenta o pouco que existia.

O efeito prático é não saber o que funciona. Os 41 acessos a /whatsapp,
/socialjobs e /sistema naquele período vieram do blog? Do X? De indicação?
Ninguém sabe, e sem saber não dá para decidir onde investir esforço.

As regras aqui são deliberadamente rígidas: um valor por rede, minúsculo, sem
acento, sem variação. Padrão frouxo produz exatamente o `ig` vs `instagram`
que já aconteceu.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Um valor por origem, para sempre. Mudar qualquer um destes quebra a série
# histórica: o analytics passa a ver duas origens onde havia uma.
FONTE = {
    "blog": "blog",
    "x": "x",
    "linkedin": "linkedin",
    "threads": "threads",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "youtube": "youtube",
}

# `medium` separa o que é publicação nossa do que é tráfego pago ou indicação.
# Tudo que a esteira emite é orgânico e social, exceto o blog, que é conteúdo
# próprio — a distinção importa na hora de comparar custo por lead.
MEIO = {"blog": "content", "youtube": "video"}
MEIO_PADRAO = "social"


def _slug(texto: str, limite: int = 100) -> str:
    """Identificador estável para a campanha, a partir do título do artigo.

    Sem acento e sem pontuação porque o valor viaja na query string e é
    agrupado como texto puro pelo analytics: "automação" e "automacao"
    virariam duas campanhas diferentes para o mesmo artigo.

    O limite era 60 e **truncava o slug no meio** (29/07/2026): o artigo
    "como-fazer-automacao-de-whatsapp-em-2026-e-vender-mais-sem-aumentar-a-equipe"
    virava campanha "...-vender-mais-sem-a". Como o Ghost gera o slug do post a
    partir do mesmo título sem esse corte, campanha e artigo deixavam de bater
    e cruzar "qual post converteu" exigia adivinhação por prefixo. 100 cobre os
    títulos que a esteira produz com folga.
    """
    import unicodedata

    limpo = unicodedata.normalize("NFKD", (texto or "").lower())
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    limpo = re.sub(r"[^a-z0-9]+", "-", limpo).strip("-")
    return limpo[:limite].rstrip("-") or "sem-titulo"


def marcar(url: str, origem: str, *, campanha: str = "", conteudo: str = "") -> str:
    """Acrescenta os parâmetros de origem a um link de funil.

    Idempotente: um link que já tem `utm_source` volta intacto. Isso importa
    porque o texto do post passa por reescrita e por refação — marcar duas
    vezes produziria `utm_source=blog&utm_source=x`, e o analytics leria o
    primeiro, atribuindo à origem errada.
    """
    if not url or not url.startswith("http"):
        return url

    partes = urlparse(url)
    atuais = dict(parse_qsl(partes.query, keep_blank_values=True))
    if "utm_source" in atuais:
        return url

    fonte = FONTE.get(origem, origem)
    atuais["utm_source"] = fonte
    atuais["utm_medium"] = MEIO.get(origem, MEIO_PADRAO)
    if campanha:
        atuais["utm_campaign"] = _slug(campanha)
    if conteudo:
        atuais["utm_content"] = _slug(conteudo, 40)

    return urlunparse(partes._replace(query=urlencode(atuais)))


# Só os funis reais recebem marcação. Marcar link de fonte externa citada no
# artigo poluiria o analytics de terceiros com o nosso rastreamento — e não
# nos diz nada, porque esse clique nunca volta.
DOMINIO_PROPRIO = "sistemabritto.com.br"


def e_funil(url: str) -> bool:
    """Verdadeiro para link de funil próprio, que vale rastrear."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith(DOMINIO_PROPRIO)


def marcar_no_texto(texto: str, origem: str, *, campanha: str = "") -> str:
    """Marca todo link de funil que aparece num texto de post.

    Opera sobre o texto pronto, e não sobre o link isolado, porque quem escreve
    o post é o modelo: ele pode citar o funil no meio de uma frase, repetir o
    link, ou usar uma variação com barra final. Varrer o texto pega todos.
    """
    if not texto:
        return texto

    def _troca(m: re.Match) -> str:
        url = m.group(0)
        return marcar(url, origem, campanha=campanha) if e_funil(url) else url

    # Para no primeiro caractere que não pertence a URL. O `)` fica de fora
    # para não engolir o fecho de um link markdown.
    return re.sub(r"https?://[^\s<>\"'\)\]]+", _troca, texto)
