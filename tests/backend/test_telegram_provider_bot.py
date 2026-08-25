from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import scripts.telegram_provider_bot as bot


class TelegramProviderBotMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        bot.CHAT_MEMORY_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_build_prompt_includes_recent_memory_and_current_message(self) -> None:
        bot.append_chat_memory("123", "user", "Quero usar NVIDIA", speaker="Felipe")
        bot.append_chat_memory("123", "assistant", "provider: nvidia", speaker="Magneto")

        prompt = bot.build_prompt("123", "e a memoria?", speaker="Felipe")

        self.assertIn("Memoria recente da conversa:", prompt)
        self.assertIn("Usuário (Felipe): Quero usar NVIDIA", prompt)
        self.assertIn("Assistente: provider: nvidia", prompt)
        self.assertIn("Mensagem atual:", prompt)
        self.assertIn("e a memoria?", prompt)

    def test_clear_chat_memory_removes_history(self) -> None:
        bot.append_chat_memory("456", "user", "oi", speaker="Felipe")
        path = bot.chat_memory_path("456")
        self.assertTrue(path.exists())

        bot.clear_chat_memory("456")

        self.assertFalse(path.exists())
        self.assertEqual(bot.load_chat_memory("456"), [])

    def test_append_chat_memory_redacts_secrets(self) -> None:
        bot.append_chat_memory("789", "user", "API key: sk-abcdefghijklmnopqrstu gsk_abcdefghijklmnopqrstu", speaker="Felipe")
        entries = bot.load_chat_memory("789")

        self.assertEqual(len(entries), 1)
        self.assertIn("[REDACTED]", entries[0]["text"])
        self.assertNotIn("sk-abcdefghijklmnopqrstu", entries[0]["text"])
        self.assertNotIn("gsk_abcdefghijklmnopqrstu", entries[0]["text"])

    def test_message_audio_file_id_detects_voice_audio_and_audio_documents(self) -> None:
        self.assertEqual(bot.message_audio_file_id({"voice": {"file_id": "voice-id"}}), "voice-id")
        self.assertEqual(bot.message_audio_file_id({"audio": {"file_id": "audio-id"}}), "audio-id")
        self.assertEqual(
            bot.message_audio_file_id({"document": {"file_id": "doc-id", "mime_type": "audio/ogg"}}),
            "doc-id",
        )
        self.assertIsNone(bot.message_audio_file_id({"document": {"file_id": "doc-id", "mime_type": "image/png"}}))

    def test_message_image_file_id_detects_photo_and_image_documents(self) -> None:
        self.assertEqual(
            bot.message_image_file_id({"photo": [{"file_id": "small", "file_size": 10}, {"file_id": "big", "file_size": 20}]}),
            ("big", ".jpg"),
        )
        self.assertEqual(
            bot.message_image_file_id({"document": {"file_id": "doc-id", "mime_type": "image/png", "file_name": "x.png"}}),
            ("doc-id", ".png"),
        )
        self.assertIsNone(bot.message_image_file_id({"document": {"file_id": "doc-id", "mime_type": "audio/ogg"}}))

    def test_read_groq_api_key_prefers_environment(self) -> None:
        original = bot.os.environ.get("GROQ_API_KEY")
        try:
            bot.os.environ["GROQ_API_KEY"] = "gsk_test_key"
            self.assertEqual(bot.read_groq_api_key(), "gsk_test_key")
        finally:
            if original is None:
                bot.os.environ.pop("GROQ_API_KEY", None)
            else:
                bot.os.environ["GROQ_API_KEY"] = original

    def test_groq_command_can_store_key_in_telegram_env(self) -> None:
        original_env = bot.TELEGRAM_ENV
        try:
            bot.TELEGRAM_ENV = bot.CHAT_MEMORY_DIR / ".env"
            response = bot.handle_groq_command("set gsk_test_key")
            self.assertEqual(response, "Groq configurado para transcricao de audio.")
            self.assertEqual(bot.read_env_value(bot.TELEGRAM_ENV, "GROQ_API_KEY"), "gsk_test_key")
            self.assertEqual(bot.handle_groq_command("status"), f"Groq configurado. Modelo de transcricao: {bot.GROQ_TRANSCRIPTION_MODEL}")
        finally:
            bot.TELEGRAM_ENV = original_env

    def test_ajuste_pendente_sobrevive_sem_reply_amarrado(self) -> None:
        """O bug real de 05/08/2026: apertar 'pedir ajuste' e depois responder
        SEM o Telegram amarrar o reply (áudio solto pela tela inicial, toque
        fora do balão) não pode cair na conversa comum. A marca em disco é
        quem resolve isso — o teste cobre só o estado, não o laço inteiro."""
        original = bot.REVISE_STATE
        try:
            bot.REVISE_STATE = bot.CHAT_MEMORY_DIR / "ajuste_pendente.json"
            self.assertIsNone(bot.ajuste_pendente("999"))

            bot.marcar_ajuste_pendente("999", 146)
            self.assertEqual(bot.ajuste_pendente("999"), 146)

            # aprovar/rejeitar limpa a marca — a próxima mensagem é conversa de novo
            bot.limpar_ajuste_pendente("999", 146)
            self.assertIsNone(bot.ajuste_pendente("999"))
        finally:
            bot.REVISE_STATE = original

    def test_ajuste_pendente_expira(self) -> None:
        original = bot.REVISE_STATE
        try:
            bot.REVISE_STATE = bot.CHAT_MEMORY_DIR / "ajuste_pendente.json"
            bot.marcar_ajuste_pendente("999", 146)
            estado = bot.read_json(bot.REVISE_STATE, {})
            estado["999"]["quando"] -= bot.REVISE_TTL_S + 1
            bot.REVISE_STATE.write_text(bot.json.dumps(estado), encoding="utf-8")

            self.assertIsNone(bot.ajuste_pendente("999"), "marca velha não pode valer para sempre")
        finally:
            bot.REVISE_STATE = original

    def test_limpar_ajuste_pendente_nao_apaga_outro_card(self) -> None:
        """Aprovar o card A não pode apagar o ajuste que o humano já tinha
        começado a pedir no card B, no mesmo chat."""
        original = bot.REVISE_STATE
        try:
            bot.REVISE_STATE = bot.CHAT_MEMORY_DIR / "ajuste_pendente.json"
            bot.marcar_ajuste_pendente("999", 146)
            bot.limpar_ajuste_pendente("999", approval_id=999)  # id errado
            self.assertEqual(bot.ajuste_pendente("999"), 146)
        finally:
            bot.REVISE_STATE = original

    def test_provider_chain_uses_strict_telegram_override(self) -> None:
        original_path = bot.PROVIDERS_PATH
        cfg = bot.CHAT_MEMORY_DIR / "providers.json"
        cfg.write_text(
            """
{
  "active_provider": "nvidia",
  "telegram_provider": "codex_auth",
  "providers": {
    "codex_auth": {"fallback_providers": ["nvidia"]},
    "nvidia": {}
  }
}
""".strip(),
            encoding="utf-8",
        )
        try:
            bot.PROVIDERS_PATH = cfg
            self.assertEqual([pid for pid, _ in bot.provider_chain()], ["codex_auth"])
            self.assertEqual(bot.provider_models("codex_auth", {}), [None])
        finally:
            bot.PROVIDERS_PATH = original_path


if __name__ == "__main__":
    unittest.main()
