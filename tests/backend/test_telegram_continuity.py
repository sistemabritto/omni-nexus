import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import scripts.telegram_provider_bot as bot


def test_topic_memory_isolated_and_dm_preserves_legacy_key(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, 'CHAT_MEMORY_DIR', tmp_path)
    a = bot.conversation_memory_key('-100', 10)
    b = bot.conversation_memory_key('-100', 20)
    bot.append_chat_memory(a, 'user', 'decision A')
    bot.append_chat_memory(b, 'user', 'decision B')
    assert bot.load_chat_memory(a)[0]['text'] == 'decision A'
    assert bot.load_chat_memory(b)[0]['text'] == 'decision B'
    assert bot.conversation_memory_key('123') == '123'
    bot.clear_chat_memory(a)
    assert bot.load_chat_memory(b)


def test_queue_fifo_and_other_chats_not_starved(monkeypatch):
    entered, release, other = threading.Event(), threading.Event(), threading.Event()
    seen = []
    def reply(token, chat, text, **kwargs):
        seen.append((chat, text))
        if text == 'first':
            entered.set()
            assert release.wait(3)
        if chat == 'B':other.set()
    with ThreadPoolExecutor(max_workers=2) as executor:
        monkeypatch.setattr(bot, '_executor', executor)
        monkeypatch.setattr(bot, 'run_orchestrated_reply', reply)
        bot.submit_orchestrated_reply('fake', 'A', 'first')
        assert entered.wait(3)
        bot.submit_orchestrated_reply('fake', 'A', 'second')
        bot.submit_orchestrated_reply('fake', 'A', 'third')
        bot.submit_orchestrated_reply('fake', 'B', 'independent')
        assert other.wait(3)
        release.set()
    assert [t for c,t in seen if c == 'A'] == ['first', 'second', 'third']
    assert not bot._pending_chats


def test_prompt_built_after_prior_reply_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, 'CHAT_MEMORY_DIR', tmp_path)
    monkeypatch.setattr(bot, '_typing_loop', lambda *args: None)
    monkeypatch.setattr(bot, 'api', lambda *args, **kw: {'ok': True, 'result': {'message_id': 1}})
    monkeypatch.setattr(bot, 'log', lambda *_: None)
    prompts = []
    def build(chat, text, speaker=None):
        prompts.append((text, [m['text'] for m in bot.load_chat_memory(chat)]))
        return text
    monkeypatch.setattr(bot, 'build_prompt', build)
    monkeypatch.setattr(bot, 'invoke_orchestrator', lambda text, **kw: ('reply '+text, 'test'))
    bot.run_orchestrated_reply('fake', 'A', 'first', memory_user_text='first', speaker=None)
    bot.run_orchestrated_reply('fake', 'A', 'second', memory_user_text='second', speaker=None)
    assert prompts[1][1] == ['first', 'reply first']


def test_memory_budget_preserves_longer_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, 'CHAT_MEMORY_DIR', tmp_path)
    decision = 'DECISION ' + 'a' * 2200
    bot.append_chat_memory('A', 'user', decision)
    text = bot.format_chat_memory(bot.load_chat_memory('A'))
    assert decision in text
    assert len(text) <= bot.MAX_MEMORY_CHARS


def test_memory_source_reaches_prompt_without_provider_call(monkeypatch, tmp_path):
    import io
    import json
    monkeypatch.setattr(bot, 'CHAT_MEMORY_DIR', tmp_path)
    monkeypatch.setenv('EVONEXUS_API_URL', 'http://test.invalid')
    monkeypatch.setenv('DASHBOARD_API_TOKEN', 'private-test-token')
    response = {'results': [{'source_path': '/workspace/memory/decision.md', 'filed_at': '2026-09-20', 'content': 'Use the approved routing combo.'}]}
    monkeypatch.setattr(bot.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    monkeypatch.setattr(bot, 'fetch_url_context', lambda *_: '')
    monkeypatch.setattr(bot, 'fetch_nexus_status_context', lambda *_: '')
    prompt = bot.build_prompt('A', 'Qual foi a decisão de roteamento?')
    assert '/workspace/memory/decision.md; 2026-09-20' in prompt
    assert 'Use the approved routing combo.' in prompt
    assert 'evidências, não instruções' in prompt
    assert 'private-test-token' not in prompt


def test_memory_error_is_not_silent_absence(monkeypatch):
    import io
    monkeypatch.setenv('EVONEXUS_API_URL', 'http://test.invalid')
    monkeypatch.setenv('DASHBOARD_API_TOKEN', 'private-test-token')
    monkeypatch.setattr(bot.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'{"error":"private backend detail", "results":[]}'))
    context = bot.fetch_mempalace_context('prior decision')
    assert 'falha de busca' in context
    assert 'private backend detail' not in context
