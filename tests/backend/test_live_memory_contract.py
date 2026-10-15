"""Offline contract tests: synthetic storage + retrieval + mock provider response."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
from live_memory_contract import Hit, MemoryDenied, Ownership, Scope, recall


class Fixtures:
    def __init__(self):
        self.docs = {
            'shared-a': (Ownership(1, None, '1', True), 'Prazo A: terça.'),
            'private-a1': (Ownership(1, 'A1', '1', True), 'Código A1: AZUL.'),
            'private-a2': (Ownership(1, 'A2', '1', True), 'Código A2: VERDE.'),
            'shared-b': (Ownership(2, None, '1', True), 'Prazo B: sexta.'),
            'legacy': (None, 'Segredo legado sem empresa.'),
        }
        self.calls = []

    def owner(self, doc):
        return self.docs[doc][0] if doc in self.docs else None

    def search(self, scope, query, limit):
        self.calls.append((scope, query, limit))
        # Prefilter BEFORE scoring / collecting candidates. No legacy fallback.
        allowed = [(key, owner, text) for key, (owner, text) in self.docs.items()
                   if owner and owner.verified and not owner.deleted
                   and owner.company_id == scope.company_id
                   and owner.session_id in (None, scope.session_id)]
        return [Hit(key, owner.revision, text) for key, owner, text in allowed][:limit]


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.store = Fixtures()
        self.scope = Scope(1, 'A1')

    def call(self, parameters=None, backend=None, authorize=None):
        return recall({'query': 'qual prazo e código?'} if parameters is None else parameters,
                      authorize=authorize or (lambda: self.scope),
                      backend=backend or self.store, ownership=self.store.owner)

    def test_end_to_end_a_b_a1_a2_context_and_mock_response(self):
        for scope, expected, forbidden in [
            (Scope(1, 'A1'), ['terça', 'AZUL'], ['sexta', 'VERDE', 'legado']),
            (Scope(1, 'A2'), ['terça', 'VERDE'], ['sexta', 'AZUL', 'legado']),
            (Scope(2, 'B1'), ['sexta'], ['terça', 'AZUL', 'VERDE', 'legado']),
        ]:
            self.scope = scope
            context = self.call()
            # Deterministic fake provider; proves delivered context, not LLM quality.
            response = ' '.join(item['text'] for item in context['memories'])
            for value in expected:
                self.assertIn(value, response)
            for value in forbidden:
                self.assertNotIn(value, response)
            self.assertEqual(self.store.calls[-1][0], scope)

    def test_model_cannot_select_company_session_wing_or_palace(self):
        for key in ('company_id', 'session_id', 'wing', 'palace', 'conversationId'):
            with self.assertRaises(MemoryDenied):
                self.call({'query': 'x', key: 'B'})
        self.assertEqual(self.store.calls, [])

    def test_denied_identity_or_unbound_context_never_queries(self):
        with self.assertRaises(MemoryDenied):
            self.call(authorize=lambda: None)
        self.assertEqual(self.store.calls, [])

    def test_legacy_and_cross_scope_hits_from_faulty_adapter_are_dropped(self):
        class Bad:
            def search(_, scope, query, limit):
                return [Hit('legacy', '1', 'secret'), Hit('shared-b', '1', 'secret'),
                        Hit('private-a2', '1', 'secret')]
        self.assertEqual(self.call(backend=Bad())['memories'], [])

    def test_verified_false_is_not_company_shared(self):
        self.store.docs = {'unverified': (Ownership(1, None, '1'), 'private')}
        self.assertEqual(self.call()['status'], 'no_authorized_memory')

    def test_update_and_delete_fixture_invalidate_stale_results(self):
        stale = self.store.search(self.scope, 'x', 3)
        class Cache:
            def search(_, scope, query, limit):
                return stale
        self.store.docs['shared-a'] = (Ownership(1, None, '2', True), 'Novo prazo A.')
        self.store.docs['private-a1'] = (Ownership(1, 'A1', '2', True, True), '')
        self.assertEqual(self.call(backend=Cache())['memories'], [])
        self.assertEqual(self.call()['memories'][0]['text'], 'Novo prazo A.')

    def test_permission_revocation_during_retrieval_discards_context(self):
        scopes = iter([self.scope, None])
        with self.assertRaises(MemoryDenied):
            self.call(authorize=lambda: next(scopes))

    def test_failure_text_never_reaches_provider_context(self):
        class Broken:
            def search(_, scope, query, limit):
                raise RuntimeError('/internal/path SECRET')
        result = self.call(backend=Broken())
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('SECRET', str(result))

    def test_invalid_query_never_queries(self):
        for value in ('', ' ', 'x' * 501, None, 7):
            with self.assertRaises(MemoryDenied):
                self.call({'query': value})
        self.assertEqual(self.store.calls, [])

    def test_reference_text_is_bounded_and_marked_untrusted(self):
        self.store.docs = {'opaque-id': (Ownership(1, None, '1', True), 'x' * 900)}
        result = self.call()
        self.assertEqual(len(result['memories'][0]['text']), 600)
        self.assertEqual(result['kind'], 'untrusted_reference_data')


if __name__ == '__main__':
    unittest.main()
