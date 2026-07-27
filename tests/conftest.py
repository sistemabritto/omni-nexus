"""Guarda de segurança da suíte: nenhum teste fala com o mundo real.

2026-07-27 — o Felipe recebeu mensagens do @evonexuslocal_bot no Telegram
durante uma rodada de testes. O `.env` da máquina de desenvolvimento tem
`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` de verdade, e qualquer teste que
chegasse a `notifications._send_telegram` sem mock enviava a mensagem para o
celular dele. É o mesmo tipo de vazamento do incidente em que o pytest acordou
um heartbeat de produção e queimou token.

O `.env` não é lido pelo pytest diretamente — mas vários módulos do backend
fazem `os.environ.get(...)` no import ou na chamada, e qualquer coisa que
carregue o `.env` no processo (uma rotina, um helper, um teste) contamina todo
o resto da sessão.

Então a suíte inteira roda com as credenciais externas neutralizadas:

- Telegram: sem token, `_send_telegram` devolve False no primeiro `if` e
  registra o motivo. Nenhuma mensagem sai.
- Provedores de LLM e imagem: sem chave, uma chamada acidental falha na hora,
  barata e ruidosa, em vez de custar tokens em silêncio.

Autouse e de escopo de sessão: não há como um teste esquecer de aplicá-lo.
Um teste que precise de uma dessas variáveis deve declará-la ele mesmo com
`monkeypatch.setenv`, que é local e explícito.
"""

from __future__ import annotations

import os

import pytest

# Tudo que, se estiver preenchido, faz um teste alcançar o mundo real.
CREDENCIAIS_NEUTRALIZADAS = (
    # Envio de mensagem — o caso concreto que motivou este arquivo
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "WHATSAPP_API_KEY",
    "WHATSAPP_PHONE",
    "EVOLUTION_GO_KEY",
    "DISCORD_BOT_TOKEN",
    # Provedores que cobram por chamada
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "AI_IMG_CREATOR_OPENAI_KEY",
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    # Publicação — um teste não pode postar nem agendar nada
    "POSTIZ_API_KEY",
    "GHOST_ADMIN_API_KEY",
    "DASHBOARD_API_TOKEN",
)


@pytest.fixture(autouse=True, scope="session")
def sem_mundo_real():
    """Roda a suíte sem nenhuma credencial externa herdada do ambiente."""
    guardadas = {k: os.environ.pop(k, None) for k in CREDENCIAIS_NEUTRALIZADAS}
    os.environ["EVONEXUS_TESTING"] = "1"
    try:
        yield
    finally:
        for chave, valor in guardadas.items():
            if valor is not None:
                os.environ[chave] = valor
        os.environ.pop("EVONEXUS_TESTING", None)
