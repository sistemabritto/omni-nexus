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
    # Existem no site desde antes desta esteira e nunca receberam um único link
    # do blog: em 76 artigos publicados, 0 apontavam para /vps ou /zapclub
    # (auditoria editorial de 02/09/2026). Pauta de infraestrutura caía em
    # /sistema, que vende PRD, não servidor — o leitor clicava esperando uma
    # coisa e encontrava outra.
    "vps": ("https://sistemabritto.com.br/vps",
            "VPS estruturada com Docker, SSL, backup e monitoramento, pronta em 24h"),
    "zapclub": ("https://sistemabritto.com.br/zapclub",
                "a comunidade de IA aplicada a negócio, com mentoria por nível"),
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
    # Infra vem antes do guarda-chuva: "onde hospedar", "servidor caindo" e
    # "quanto custa manter" são a dor que /vps resolve, e mandá-las para a call
    # de PRD é oferecer escopo a quem quer máquina de pé.
    if any(t in texto for t in ("vps", "servidor", "hospedagem", "hospedar", "deploy",
                                "docker", "self-host", "self host", "infraestrutura",
                                "backup", "uptime")):
        return "vps"
    if any(t in texto for t in ("comunidade", "mentoria", "aprender ia", "estudar ia",
                                "curso de ia", "por onde começar", "por onde comecar")):
        return "zapclub"
    return "sistema"


def _funil_para(keyword: str) -> tuple[str, str]:
    """URL e descrição do funil da pauta."""
    return FUNIS[funil_de(keyword)]


# O que o artigo tem de provar, por pilar da tese RASTREAR → VIBE CODAR →
# MONETIZAR. Existe porque a auditoria editorial de 02/09/2026 mediu o blog
# inteiro contra a tese e achou o resultado abaixo, em 76 artigos publicados:
# 0 mencionavam Vibe Seller, 0 citavam JURISMART, Voice Dream, Laboratório de
# Insights ou Omni Nexus, 0 falavam de comoditização, moat, licenciamento,
# equity ou build vs buy, e 1 citava o nome do fundador. O prompt descrevia a
# empresa como "vende automação e operação com IA para donos de empresa" e o
# blog saiu exatamente disso: um catálogo de ferramentas.
#
# Pilar não é decoração de prompt: é o que separa "como configurar X" (que
# qualquer LLM responde de graça) de "onde a sua operação perde dinheiro com
# X" (que só quem opera consegue escrever).
PILARES = {
    "RASTREAR": (
        "onde a operação do leitor perde dinheiro hoje: gargalo, receita não "
        "capturada, retrabalho caro, custo que ninguém mede. O artigo tem de "
        "ensinar a ENCONTRAR o problema, com sinais observáveis e uma conta de "
        "guardanapo que o leitor consiga refazer com os números dele."
    ),
    "VIBE CODAR": (
        "como se constrói a solução específica: arquitetura, decisão entre "
        "montar e comprar, open source, agente, integração, infraestrutura. "
        "Sempre com o custo real de manter, nunca só o de montar."
    ),
    "MONETIZAR": (
        "como o valor construído vira dinheiro: receita, receita recuperada, "
        "conversão, economia, margem, trabalho operacional que deixou de "
        "existir, licenciamento, propriedade intelectual, equity ou parceria. "
        "Terminar sem dizer quem captura o valor é deixar o artigo pela metade."
    ),
}


def pilar_de(keyword: str) -> str:
    """Pilar da tese a que a pauta pertence.

    Regra explícita, como `funil_de`, e pela mesma razão: deixar o modelo
    escolher produz sempre o pilar do meio, que é o mais fácil de escrever e o
    menos diferenciado. "Como configurar" é o gênero que a concorrência inteira
    já publicou.
    """
    texto = keyword.lower()
    if any(t in texto for t in ("quanto custa", "custo", "preço", "preco", "vale a pena",
                                "erro", "risco", "perder", "perde", "medir", "métrica",
                                "metrica", "diagnóstico", "diagnostico", "gargalo",
                                "por que", "onde")):
        return "RASTREAR"
    if any(t in texto for t in ("receita", "faturamento", "margem", "lucro", "conversão",
                                "conversao", "vender", "venda", "vendas", "monetiz",
                                "licenc", "economia", "economizar", "reduzir custo",
                                "roi", "equity")):
        return "MONETIZAR"
    return "VIBE CODAR"


# Quantos artigos publicados o prompt oferece como destino de link interno.
# Mais que isso e o modelo escolhe o que parece relacionado pelo título em vez
# do que é relacionado pelo assunto; menos e a maioria das pautas não acha par.
MAXIMO_DE_RELACIONADOS = 8


def _bloco_links_internos(relacionados: list[dict] | None) -> str:
    """Lista de artigos publicados que este texto deve linkar.

    Existe porque a auditoria de 02/09/2026 contou os links internos do blog e
    achou zero: 76 artigos publicados, nenhum apontando para outro. O leitor
    chegava por busca, lia um texto e não tinha para onde ir a não ser voltar,
    e o buscador via 76 páginas órfãs em vez de um conjunto sobre um assunto.

    Os candidatos vêm de fora (a rotina já fala com o Ghost) em vez de serem
    buscados aqui: manter `escrever` sem chamada de rede é o que deixa o teste
    rodar sem tocar em produção.
    """
    if not relacionados:
        return ""
    linhas = "\n".join(
        f"- {r['titulo']} → https://blog.sistemabritto.com.br/{r['slug']}/"
        for r in relacionados[:MAXIMO_DE_RELACIONADOS]
    )
    return (
        "LINKS INTERNOS OBRIGATÓRIOS (2 a 3, dentro do corpo do texto, nunca "
        "numa lista de 'leia também' no fim):\n"
        f"{linhas}\n"
        "Só linke o que a frase realmente pede. Âncora descreve o destino em 2 "
        "a 5 palavras. Não invente URL que não esteja nesta lista.\n\n"
    )


def _briefing_humanizer() -> str:
    if HUMANIZER.is_file():
        return HUMANIZER.read_text(encoding="utf-8", errors="replace")[:6000]
    log.warning("humanizer.md não encontrado em %s — artigo sai sem o guia", HUMANIZER)
    return ""


def montar_prompt(pauta: dict, noticia: str = "",
                  relacionados: list[dict] | None = None) -> str:
    from datetime import date

    keyword = pauta["keyword"]
    funil_url, funil_desc = _funil_para(keyword)
    pilar = pilar_de(keyword)
    hoje = date.today()
    return (
        "Você escreve um artigo de blog em português do Brasil para a Sistema "
        "Britto. Devolva um JSON com as chaves titulo, meta_title, "
        "meta_description, excerpt, tags e html — nada além do JSON.\n\n"

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

        # Ghost cai no título e no excerpt quando estes campos estão vazios, e
        # foi o que aconteceu em 75 dos 76 artigos publicados: o buscador
        # recebia o título inteiro, às vezes com 90 caracteres, cortado no meio.
        "METADADOS (campos separados no JSON, não dentro do html):\n"
        "- meta_title: até 60 caracteres, com a palavra-chave, diferente do "
        "titulo quando o titulo passar de 60.\n"
        "- meta_description: 120 a 155 caracteres. Responde a pergunta do "
        "título e diz o que o leitor sai sabendo. Não é chamada de venda.\n"
        "- tags: lista de 2 a 4 slugs em minúsculas com hífen. A primeira é "
        f"sempre o pilar: {pilar.lower().replace(' ', '-')}. As outras "
        "descrevem o assunto.\n\n"

        f"CTA OBRIGATÓRIO no último parágrafo, apontando para {funil_url} "
        f"({funil_desc}). Um só, específico, ligado ao que o artigo acabou de ensinar.\n"
        # O texto do link é o que o leitor lê antes de decidir clicar, e é o que
        # o Google usa pra entender o destino. "Clique aqui" desperdiça os dois:
        # não diz o que tem do outro lado e não descreve a página. Saía assim
        # nos posts de 28-29/07/2026 até esta instrução existir.
        "- O texto do link (âncora) diz O QUE a pessoa encontra do outro lado, "
        "em 2 a 5 palavras. Ex.: 'ver como montamos o fluxo', 'a call que produz "
        "o PRD'.\n"
        "- PROIBIDO como texto de link: 'clique aqui', 'saiba mais', 'confira', "
        "'acesse', 'veja mais', ou o link cru exposto.\n\n"

        + _bloco_links_internos(relacionados)

        + f"PILAR DESTE ARTIGO: {pilar}.\n{PILARES[pilar]}\n\n"

        "POSICIONAMENTO (o que separa este blog de um catálogo de ferramentas):\n"
        "- A tese é RASTREAR, VIBE CODAR, MONETIZAR. Um Vibe Coder consegue "
        "construir; um Vibe Seller rastreia oportunidade de negócio, identifica "
        "valor não capturado, constrói quando faz sentido e encontra a forma de "
        "capturar esse valor.\n"
        "- Escreva de dentro da operação, não de fora. Quem escreve construiu e "
        "vendeu, veio de marketing e vendas, e parte do problema comercial, não "
        "da tecnologia.\n"
        "- Todo artigo responde, em algum ponto, quem captura o valor: em "
        "receita, receita recuperada, conversão, economia, margem, trabalho "
        "operacional que some, licenciamento, propriedade intelectual, equity "
        "ou parceria.\n"
        "- Ferramenta é meio. Antes de recomendar software: localize o valor, "
        "entenda o problema, avalie distribuição e defensabilidade, e só então "
        "decida entre construir e comprar. Diga também quando NÃO vale "
        "construir, e qual o risco de a diferenciação ser comoditizada por IA "
        "ou open source.\n"
        "- Separe o que é EVIDÊNCIA (dado com fonte), HIPÓTESE (leitura "
        "plausível a testar) e OPINIÃO. Atenção não é intenção, e intenção não "
        "é compra.\n\n"

        # A regra de "não invente" já existia e continuava sendo obedecida, mas
        # ela sozinha produziu 76 artigos sem uma única história real: o modelo
        # não inventa caso, e também não conhece nenhum. Sem a lista abaixo no
        # prompt, o texto só tem o que qualquer LLM já sabe.
        "CASOS REAIS QUE PODEM SER CITADOS (só estes, e só como contexto "
        "informado pelo fundador):\n"
        "- Laboratório de Insights: software com IA que chegou a cerca de 70 "
        "usuários, não sustentou unit economics e não reteve na renovação.\n"
        "- JURISMART: gerador de petições cuja diferenciação foi comprimida "
        "pela popularização do ChatGPT antes de capturar mercado. O nome é "
        "JURISMART, nunca outro.\n"
        "- Voice Dream: tecnologia construída com IA a partir de oportunidade "
        "do sócio, com investimento seed informado pelo fundador.\n"
        "- Omni Nexus: o sistema operacional multiagente que opera a própria "
        "Sistema Britto, incluindo esta esteira de conteúdo.\n"
        "Cite no máximo um caso, e só quando ele explicar o ponto do artigo. "
        "Caso citado fora de lugar vira propaganda. É PROIBIDO inventar "
        "número, cliente, depoimento, credencial ou resultado, e é PROIBIDO "
        "atribuir a esses casos qualquer métrica que não esteja escrita acima.\n\n"

        "MARCA:\n"
        "- Tom direto, de quem construiu. Nunca de quem vende.\n"
        "- PROIBIDO: 'juntos vamos', 'revolucionar', 'transformação digital', "
        "'disruptivo', 'garanta já', 'últimas vagas', promessa de resultado sem dado.\n"
        # O travessão é correto em português, mas hoje ele lê como assinatura de
        # texto gerado — foi a primeira coisa que o Felipe apontou ao revisar as
        # páginas do site. Percepção do leitor decide, não a gramática.
        "- NUNCA use travessão (— ou –). Reescreva a frase com vírgula, ponto ou "
        "dois-pontos. Hífen só dentro de palavra composta.\n"
        "- Nunca invente número, data, caso de cliente ou métrica.\n\n"

        f"GUIA ANTI-ESCRITA-DE-IA (obrigatório, não é sugestão):\n{_briefing_humanizer()}"
    )


# Texto de link que não diz nada sobre o destino. Ordenado do mais específico
# para o mais genérico: "clique aqui e veja X" precisa casar antes de "clique
# aqui", senão sobra o resto da frase pendurado.
ANCORAS_VAZIAS = re.compile(
    r"^\s*(?:"
    r"clique\s+aqui(?:\s+e\s+\w+.*)?|aqui|"
    r"saiba\s+mais|veja\s+mais|leia\s+mais|confira(?:\s+aqui)?|"
    r"acesse(?:\s+aqui)?|acesso|link|este\s+link|neste\s+link|"
    r"ver\s+mais|clique|"
    r"https?://\S+"
    r")\s*[.!:]?\s*$",
    re.IGNORECASE,
)

# O que entra no lugar, por funil. Diz o que a pessoa encontra do outro lado,
# que é o trabalho que "clique aqui" não faz.
ANCORA_POR_FUNIL = {
    "whatsapp": "ver como montamos o atendimento",
    "socialjobs": "ver a operação de conteúdo por dentro",
    "sistema": "a call de 1h que produz o PRD",
    "vps": "a VPS já estruturada",
    "zapclub": "a comunidade por dentro",
}


def ancora_util(html: str, keyword: str = "") -> str:
    """Troca texto de link genérico por um que descreve o destino.

    "Clique aqui" desperdiça as duas funções do texto de um link: dizer ao
    leitor o que tem do outro lado, e dizer ao buscador do que trata a página
    de destino. Saiu assim nos posts de 28 e 29/07/2026 ("Clique aqui",
    "clique aqui e veja as estruturas que usamos") mesmo com a instrução no
    prompt, que é o padrão já conhecido: instrução negativa não vence hábito
    de treino, precisa de rede embaixo (mesma razão de `sem_travessao`).

    Só mexe em link de funil próprio. Âncora ruim em link externo é problema
    do site de destino, não nosso, e reescrever citação alheia seria pior.
    """
    if not html:
        return html

    substituto = ANCORA_POR_FUNIL.get(funil_de(keyword) if keyword else "", "ver como a gente faz")

    def _troca(m: re.Match) -> str:
        abertura, texto = m.group(1), m.group(2)
        if "sistemabritto.com.br" not in abertura:
            return m.group(0)
        if not ANCORAS_VAZIAS.match(texto.strip()):
            return m.group(0)
        return f"{abertura}{substituto}</a>"

    return re.sub(r"(<a\b[^>]*>)(.*?)</a>", _troca, html, flags=re.IGNORECASE | re.DOTALL)


def sem_travessao(texto: str) -> str:
    """Troca travessão por pontuação comum.

    A proibição já está no prompt, mas o modelo desobedece: travessão é o que
    ele mais usa para encaixar aposto, e uma instrução negativa não vence um
    hábito de treino. Esta é a rede embaixo — o prompt evita a maioria, isto
    garante o resto.

    ` — ` vira `, ` porque em português o travessão de aposto e o de explicação
    aceitam vírgula no lugar sem mudar o sentido. Travessão colado (`palavra—
    palavra`) só some, senão sobra vírgula onde não havia pausa.
    """
    if not texto:
        return texto
    # Entre dígitos é intervalo ("2020—2024"), e ali o certo é hífen, não vírgula.
    limpo = re.sub(r"(?<=\d)\s*[—–]\s*(?=\d)", "-", texto)
    # Entre palavras, com ou sem espaço em volta: vírgula. Colar as duas
    # palavras ("redes—uma" virando "redesuma") seria pior que o travessão.
    limpo = re.sub(r"\s*[—–]\s*(?=\w)", ", ", limpo)
    limpo = re.sub(r"[—–]", "", limpo)             # sobra no fim de linha ou solto
    # ", ," sai de "x, — y"; ", ." de travessão antes do ponto final.
    limpo = re.sub(r",\s*([,.;:!?])", r"\1", limpo)
    # O travessão no fim da frase deixa espaço pendurado antes do </p>.
    limpo = re.sub(r"[ \t]+(?=<|$)", "", limpo)
    return limpo


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

# Limites do que os buscadores mostram sem cortar. Não são regra de estilo:
# passar disso não é erro de validação, é texto que o leitor nunca lê.
LIMITE_META_TITLE = 60
LIMITE_META_DESCRIPTION = 155


def _meta_title(artigo: dict, titulo: str) -> str:
    """meta_title do modelo, ou o título cortado na palavra.

    Fail-open de propósito: artigo bom não é descartado por causa de um campo
    de metadado, e o título truncado ainda é melhor que o campo vazio, que era
    o estado de 75 dos 76 artigos publicados.
    """
    bruto = sem_travessao((artigo.get("meta_title") or "").strip())
    if bruto and len(bruto) <= LIMITE_META_TITLE:
        return bruto
    base = sem_travessao(titulo)
    if len(base) <= LIMITE_META_TITLE:
        return base
    corte = base[:LIMITE_META_TITLE].rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:")


def _meta_description(artigo: dict, titulo: str) -> str:
    """meta_description do modelo, cortada no limite, ou vazia.

    Aqui a vazia é aceitável: o Ghost cai no excerpt, que a esteira preenche.
    Inventar descrição a partir do título só duplicaria o que o buscador já tem.
    """
    bruto = sem_travessao((artigo.get("meta_description") or "").strip())
    if not bruto:
        return ""
    if len(bruto) <= LIMITE_META_DESCRIPTION:
        return bruto
    return bruto[:LIMITE_META_DESCRIPTION].rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _tags(artigo: dict, keyword: str) -> list[str]:
    """Tags do artigo, sempre começando pelo pilar.

    O pilar entra por código e não por confiança no modelo porque ele é a
    navegação do blog: /tag/rastrear, /tag/vibe-codar e /tag/monetizar são o
    que transforma 76 páginas soltas em três conjuntos. Errar o pilar em um
    artigo desalinha a arquitetura inteira.
    """
    pilar = pilar_de(keyword).lower().replace(" ", "-")
    saida = [pilar]
    for t in (artigo.get("tags") or []):
        slug = re.sub(r"[^a-z0-9]+", "-", str(t).strip().lower()).strip("-")
        if slug and slug not in saida:
            saida.append(slug)
        if len(saida) == 4:
            break
    return saida


def escrever(pauta: dict, *, noticia: str = "",
             relacionados: list[dict] | None = None) -> tuple[dict, str]:
    """Gera o artigo da pauta. Devolve (artigo, erro).

    `artigo` traz titulo, excerpt e html. Fail-closed: texto curto demais ou
    sem CTA de funil não é devolvido como sucesso — melhor a rotina registrar
    a falha e o slot ficar vazio do que publicar um artigo pela metade.
    """
    from ghost_publisher import _pedir_ao_modelo

    bruto = _pedir_ao_modelo(montar_prompt(pauta, noticia, relacionados), timeout=420)
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

    html = sem_travessao(html)
    titulo = sem_travessao(titulo)
    # Antes de marcar a UTM: o guard olha o texto do link, e a marcação mexe
    # só no href. Rodar depois também funcionaria, mas rodar aqui mantém o
    # bloco de "limpeza de texto" junto e a marcação de origem separada.
    html = ancora_util(html, pauta.get("keyword", ""))

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
        "meta_title": _meta_title(artigo, titulo),
        "meta_description": _meta_description(artigo, titulo),
        "excerpt": sem_travessao((artigo.get("excerpt") or "").strip())[:300],
        "tags": _tags(artigo, pauta["keyword"]),
        "pilar": pilar_de(pauta["keyword"]),
        "html": html,
        "palavras": palavras,
    }, ""
