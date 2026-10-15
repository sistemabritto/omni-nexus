# Contraste: limites e referência verificável

Texto e exemplo local original OmniNexus, 2026-10-15. Corrige os pontos identificados no upstream; nenhum checker upstream foi instalado ou executado.

Fontes primárias: [W3C SC 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) e [luminância relativa](https://www.w3.org/WAI/GL/wiki/Relative_luminance). Os limiares não são arredondáveis: 4,499 falha para texto normal. Grande significa pelo menos 18pt/24 CSS px regular, ou 14pt/56÷3 CSS px negrito. Negrito aqui é informado pelo avaliador com base na fonte efetiva, não inferido do texto.

O exemplo abaixo é um validador puro de referência para pares sRGB hex opacos. Não tem CLI, daemon, dependências ou efeito de arquivo/rede. Os testes do repositório validam este bloco. Ele não é ferramenta MCP instalada. Recusa alpha/nomes CSS em vez de fingir composição; extrair o fundo real antes de usar. Razão mantém precisão para o veredito; arredondar só a apresentação.

```python
import math
import re


def luminance(color):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color):
        raise ValueError("Use #RGB ou #RRGGBB opaco")
    h = color[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), linear))


def contrast_ratio(foreground, background):
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def assess_ratio(ratio, font_size_px, bold=False):
    if not math.isfinite(ratio) or not 1 <= ratio <= 21:
        raise ValueError("Razão fora de 1..21")
    if not math.isfinite(font_size_px) or font_size_px <= 0 or not isinstance(bold, bool):
        raise ValueError("Tamanho positivo e bold booleano são obrigatórios")
    large = font_size_px >= 24 or (bold and font_size_px >= 56 / 3)
    threshold = 3.0 if large else 4.5
    return {"ratio": ratio, "large_text": large, "threshold": threshold, "pass": ratio >= threshold}
```

Registrar par real, tamanho/peso, razão bruta, limiar, resultado e contexto. #777777 sobre branco fica abaixo de 4,5:1. Exceções normativas (como logotipos) não autorizam mudança de marca nem dispensam análise de controles interativos. Segurança, zoom, foco, semântica e reflow precisam de inspeção própria.
