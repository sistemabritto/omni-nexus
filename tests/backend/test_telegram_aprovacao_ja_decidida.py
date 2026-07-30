"""A ponte de ajuste não pode engolir mensagem de card já decidido.

Incidente real 30/07/2026: um áudio pedindo para publicar um arquivo como
artefato foi enviado em reply ao card da aprovação 77, aprovada minutos antes.
O bridge devolveu 409, o bot respondeu "Já decidido antes — nada mudou" e o
pedido nunca chegou ao orquestrador. Log da VPS:

    approval-revise chat=781340724 approval=77 audio=True ok=False

O reply no celular é atalho de citação, não declaração de intenção sobre o
gate. Com o gate fechado, a única leitura útil da mensagem é "pedido novo".
"""
from __future__ import annotations

import io
import unittest
import urllib.error
from unittest import mock

import scripts.telegram_provider_bot as bot


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://x/api/approvals/77/decision", code=code, msg="conflict",
        hdrs=None, fp=io.BytesIO(b'{"error":"already decided"}'),
    )


class AprovacaoJaDecididaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(
            bot.os.environ,
            {"EVONEXUS_API_URL": "http://dash:8080", "APPROVAL_BRIDGE_TOKEN": "t"},
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_409_sinaliza_already_decided(self) -> None:
        """409 tem de ser distinguível de erro genérico, senão o bot não sabe
        que pode devolver a mensagem ao orquestrador."""
        with mock.patch.object(bot.urllib.request, "urlopen", side_effect=_http_error(409)):
            resp = bot.decide_approval_via_api(77, "revise", "781340724", feedback="oi")

        self.assertFalse(resp["ok"])
        self.assertTrue(resp["already_decided"])

    def test_erro_generico_nao_marca_already_decided(self) -> None:
        """Um 500 é falha de verdade — devolver ao orquestrador ali esconderia
        o erro e perderia a crítica legítima."""
        with mock.patch.object(bot.urllib.request, "urlopen", side_effect=_http_error(500)):
            resp = bot.decide_approval_via_api(77, "revise", "781340724", feedback="oi")

        self.assertFalse(resp["ok"])
        self.assertFalse(resp.get("already_decided", False))

    def test_sucesso_nao_marca_already_decided(self) -> None:
        corpo = io.BytesIO(b'{"ok": true}')
        corpo.__enter__ = lambda s=corpo: s  # type: ignore[attr-defined]
        corpo.__exit__ = lambda *a: None  # type: ignore[attr-defined]
        with mock.patch.object(bot.urllib.request, "urlopen", return_value=corpo):
            resp = bot.decide_approval_via_api(77, "revise", "781340724", feedback="oi")

        self.assertTrue(resp["ok"])
        self.assertFalse(resp.get("already_decided", False))


if __name__ == "__main__":
    unittest.main()
