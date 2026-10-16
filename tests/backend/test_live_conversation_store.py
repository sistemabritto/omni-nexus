"""Temporary SQLite fixtures only; provider output and reconnect are simulated."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard/backend'))
from live_conversation_store import ConversationStore, ContinuityDenied, Principal


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'continuity.sqlite3'
        self.revoked = set()
        self.allowed = lambda p, cid: p.user_id != 'disabled' and cid not in self.revoked
        self.store = ConversationStore(self.path, self.allowed)
        self.a = Principal('user1', 1)
        self.b = Principal('user1', 2)
        self.other = Principal('user2', 1)

    def record(self, cid, text='Decisão A', **kwargs):
        return self.store.record(self.a, cid, kind=kwargs.pop('kind', 'decision'),
                                 text=text, source='explicit-user:fixture', **kwargs)

    def test_reload_reconnect_voice_change_resume_persisted_conversation(self):
        self.assertIsNone(self.store.latest(self.a))
        cid = self.store.create_explicit(self.a)
        self.record(cid, 'Prazo: terça', kind='fact', verified=True)
        self.record(cid, 'Enviar proposta', kind='pending', verified=True)
        self.record(cid, 'Prefere respostas curtas', kind='preference', verified=True)
        for connection in ('reconnect', 'reload', 'voice_changed'):
            reloaded = ConversationStore(self.path, self.allowed)
            self.assertEqual(reloaded.latest(self.a), cid)
            snapshot = reloaded.snapshot(self.a, cid)
            # Mock provider receives only current data, not audit revisions.
            reply = ' '.join(e['text'] for e in snapshot['current_context'])
            self.assertIn('terça', reply)
            self.assertIn('Enviar proposta', reply)
            self.assertEqual(len(snapshot['summary']['preferences']), 1)

    def test_new_conversation_requires_explicit_method_and_is_latest(self):
        a1 = self.store.create_explicit(self.a)
        self.record(a1)
        a2 = self.store.create_explicit(self.a)
        self.assertEqual(self.store.latest(self.a), a2)
        self.assertEqual(self.store.snapshot(self.a, a2)['current_context'], [])
        self.assertEqual(len(self.store.snapshot(self.a, a1)['current_context']), 1)

    def test_user_company_and_conversation_isolation(self):
        a1 = self.store.create_explicit(self.a)
        self.record(a1, 'SEGREDO A1', verified=True)
        a2 = self.store.create_explicit(self.a)
        self.record(a2, 'SEGREDO A2', verified=True)
        b = self.store.create_explicit(self.b)
        other = self.store.create_explicit(self.other)
        for principal in (self.b, self.other):
            with self.assertRaises(ContinuityDenied):
                self.store.snapshot(principal, a1)
            with self.assertRaises(ContinuityDenied):
                self.store.record(principal, a1, kind='fact', text='bad', source='fixture')
        self.assertEqual(self.store.latest(self.b), b)
        self.assertEqual(self.store.latest(self.other), other)
        self.assertNotIn('SEGREDO A1', str(self.store.snapshot(self.a, a2)))
        self.assertNotIn('SEGREDO A2', str(self.store.snapshot(self.a, a1)))

    def test_revoked_session_never_resumes_or_returns_context(self):
        older = self.store.create_explicit(self.a)
        newest = self.store.create_explicit(self.a)
        self.revoked.add(newest)
        self.assertEqual(self.store.latest(self.a), older)
        with self.assertRaises(ContinuityDenied):
            self.store.snapshot(self.a, newest)
        with self.assertRaises(ContinuityDenied):
            self.record(newest)

    def test_revoked_identity_no_database_creation(self):
        with self.assertRaises(ContinuityDenied):
            self.store.create_explicit(Principal('disabled', 1))
        self.assertFalse(self.path.exists())

    def test_claims_and_preferences_are_inferences_until_confirmed(self):
        cid = self.store.create_explicit(self.a)
        pref = self.record(cid, 'Gosta de azul', kind='preference')
        snap = self.store.snapshot(self.a, cid)
        self.assertEqual(snap['summary']['preferences'], [])
        self.assertEqual(len(snap['summary']['inferences']), 1)
        self.record(cid, 'Gosta de verde', kind='preference', verified=True,
                    event_id=pref['event_id'], expected_revision=1)
        snap = self.store.snapshot(self.a, cid)
        self.assertEqual(snap['summary']['inferences'], [])
        self.assertEqual(snap['summary']['preferences'][0]['revision'], 2)
        self.assertEqual(snap['summary']['preferences'][0]['source'], 'explicit-user:fixture')
        self.assertNotIn('azul', str(snap['current_context']))
        self.assertIn('azul', str(snap['history']))  # explicit audit, never provider payload

    def test_correction_and_retraction_refresh_summary_atomically(self):
        cid = self.store.create_explicit(self.a)
        item = self.record(cid, 'Prazo terça', verified=True)
        self.record(cid, 'Prazo quarta', verified=True, event_id=item['event_id'], expected_revision=1)
        with self.assertRaisesRegex(ValueError, 'revision_conflict'):
            self.record(cid, 'stale', event_id=item['event_id'], expected_revision=1)
        self.record(cid, 'Retirado pelo usuário', event_id=item['event_id'], expected_revision=2, retract=True)
        snap = self.store.snapshot(self.a, cid)
        self.assertEqual(snap['summary']['decisions'], [])
        self.assertEqual(snap['current_context'], [])
        self.assertEqual(len(snap['history']), 3)
        self.assertGreater(snap['summary_revision'], 1)

    def test_mid_write_revocation_rolls_back_event_and_summary(self):
        cid = self.store.create_explicit(self.a)
        calls = []
        def allowed(p, c):
            calls.append(c)
            return len(calls) < 3
        self.store.allowed = allowed
        with self.assertRaises(ContinuityDenied):
            self.record(cid, 'must rollback')
        self.store.allowed = self.allowed
        self.assertEqual(self.store.snapshot(self.a, cid)['history'], [])

    def test_unknown_conversation_and_invalid_model_claims(self):
        with self.assertRaises(ContinuityDenied):
            self.store.snapshot(self.a, 'unknown')
        cid = self.store.create_explicit(self.a)
        with self.assertRaises(ValueError):
            self.record(cid, kind='inference', verified=True)
        with self.assertRaises(ValueError):
            self.record(cid, event_id='fabricated', expected_revision=1)
        with self.assertRaises(ValueError):
            self.store.snapshot(self.a, cid, history_limit=999)

    def test_search_ranks_coverage_excludes_exact_question_and_preserves_acl(self):
        cid = self.store.create_explicit(self.a)
        verified = self.record(cid, 'roteiro video aprovado', verified=True)
        for i in range(105):
            self.store.record(self.a, cid, kind='transcript', text='roteiro saudação',
                              source='browser:assistant:fixture')
        question = self.store.record(self.a, cid, kind='transcript', text='roteiro video pergunta',
                                     source='browser:user:fixture')
        foreign = self.store.create_explicit(self.other)
        self.store.record(self.other, foreign, kind='decision', text='roteiro video SECRET', source='fixture', verified=True)
        denied = self.store.create_explicit(self.a)
        self.record(denied, 'roteiro video REVOKED', verified=True)
        self.revoked.add(denied)
        hits = self.store.search(self.a, ['roteiro', 'video'], exclude_event=(cid, question['event_id']))
        self.assertEqual(hits[0]['event_id'], verified['event_id'])
        self.assertEqual(len(hits), 5)
        self.assertNotIn(question['event_id'], [h['event_id'] for h in hits])
        self.assertNotIn('SECRET', str(hits))
        self.assertNotIn('REVOKED', str(hits))
        # An event ID in another logical conversation must not be excluded by ID alone.
        other = self.store.create_explicit(self.a)
        record = self.record(other, 'roteiro video outro', verified=True)
        self.assertIn(record['event_id'], [h['event_id'] for h in self.store.search(
            self.a, ['roteiro', 'video'], exclude_event=(cid, record['event_id']))])
        with self.assertRaises(ValueError):
            self.store.search(self.a, ['roteiro'], exclude_event=('invalid',))


if __name__ == '__main__':
    unittest.main()
