"""Small deterministic lexical query policy shared by authorized Live sources."""
import re
import unicodedata


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value) if not unicodedata.combining(c))


# Conversational scaffolding and temporal requests are not useful OR-search terms.
_STOP = frozenset('''qual quais sobre anterior anteriores lembra voce para como que uma
um uns umas dos das meu meus minha minhas seu seus sua suas tem tenho temos ter
pode podem poderia consegue conseguir gostaria quero queria saber dizer fala falar
mostra mostrar busca buscar consulta consultar encontra encontrar acesso esta estar
foi feito fizemos trabalho trabalhos ultimo ultimos ultima ultimas hoje ontem agora
por favor aqui ainda entao sim nao esse essa esses essas isso isto algo algum alguma
me mim nos nosso nossa nossas nossos sem com pelo pela porque onde quando seria'''.split())
# Explicit source nouns take precedence over scaffolding before the four-term cap.
_SUBJECTS = frozenset(('roteiro', 'video', 'arquivo', 'documento', 'historico', 'ajudante'))
_PLURALS = {'roteiros':'roteiro', 'vídeos':'vídeo', 'videos':'video', 'arquivos':'arquivo',
            'documentos':'documento', 'históricos':'histórico', 'historicos':'historico',
            'ajudantes':'ajudante'}


def query_terms(query):
    tokens = re.findall(r'[^\W_]+(?:-[^\W_]+)*', query.strip()[:200].lower())
    tokens = list(dict.fromkeys(_PLURALS.get(t, t) for t in tokens))
    useful = [t for t in tokens if len(t) >= 3 and _fold(t) not in _STOP]
    return sorted(useful, key=lambda t: _fold(t) not in _SUBJECTS)[:4]
