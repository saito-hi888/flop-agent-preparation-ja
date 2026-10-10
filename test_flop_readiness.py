import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import flop_agent as agent
import flop_watch as watch
import flop_tasks as tasks
import flop_activity as activity

class RegistrationTests(unittest.TestCase):
    def run_verify(self, note_response):
        seed = bytes(range(32))
        did = agent._did(seed)
        _, sig = agent._sign_room(seed, 'lobby', '123', 'hello')
        registration = {'did': did, 'did_note': 'https://technocore.chat/kv/evil/key/set/mutation', 'room': 'lobby', 'nonce': '123', 'message': 'hello', 'signature': sig, 'posted': {'seq': 1, 'from': did}}
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'registration.json'
            file.write_text(json.dumps(registration))
            with patch.object(agent, 'REGISTRATION_FILE', file), patch.object(agent, '_load_seed', return_value=seed), patch.object(agent, '_request', side_effect=[note_response, '{"messages":[]}']) as request:
                result = agent.verify_registration()
                self.assertNotIn('/set/', request.call_args_list[0].args[0])
                return result
    def test_missing_note_keeps_local_identity_verifiable(self):
        result = self.run_verify(agent.RemoteHTTPError(404, 'expired'))
        self.assertTrue(result['local_signature_verified'])
        self.assertFalse(result['remote_did_note_verified'])
        self.assertEqual(result['remote_did_note_status'], 'missing-or-expired')
        self.assertFalse(result['allocation_verified'])
    def test_network_failure_is_not_expiry(self):
        with self.assertRaises(agent.RemoteHTTPError):
            self.run_verify(agent.RemoteHTTPError(503, 'unavailable'))
    def test_mismatching_note_is_not_accepted(self):
        with self.assertRaises(agent.FlopAgentError):
            self.run_verify('warning\n\ndid:key:other purpose:flop-testnet-preparation')

class MonitorTests(unittest.TestCase):
    PAGE = '<html><h1>FLOP testnet status draft</h1><p>' + 'Readiness criteria are provisional. ' * 4 + '</p></html>'
    def test_baseline_change_and_failure_preserve_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(watch.SOURCES, {'testnet': 'https://flop.finance/testnet/'}, clear=True):
            path = Path(tmp)
            first = watch.check(path, lambda url: self.PAGE)
            self.assertEqual(first['results'][0]['status'], 'baseline')
            same = watch.check(path, lambda url: self.PAGE)
            self.assertEqual(same['results'][0]['status'], 'unchanged')
            changed = watch.check(path, lambda url: self.PAGE.replace('draft', 'updated'))
            self.assertEqual(changed['results'][0]['status'], 'changed')
            before = (path / 'testnet.txt').read_text()
            def fail(url):
                raise OSError('offline')
            failed = watch.check(path, fail)
            self.assertEqual(failed['results'][0]['status'], 'error')
            self.assertEqual((path / 'testnet.txt').read_text(), before)
            self.assertEqual(failed['retained_change_events'], 1)
    def test_script_changes_do_not_trigger_content_changes(self):
        self.assertEqual(watch.normalize(self.PAGE+'<script>abc</script>', 'testnet'), watch.normalize(self.PAGE+'<script>xyz</script>', 'testnet'))
    def test_unexpected_body_does_not_replace_snapshot(self):
        with self.assertRaises(ValueError):
            watch.normalize('<h1>Cloudflare challenge</h1>', 'testnet')
    def test_unlisted_endpoint_never_requested(self):
        with self.assertRaises(ValueError):
            watch.fetch('https://technocore.chat/kv/ns/key/set/write')

class ReceiptTests(unittest.TestCase):
    def receipt(self):
        return {'network_genesis_hash': 'test-genesis', 'wallet_address': 'test-address', 'session_id': 'test-session', 'transaction_id': 'test-transaction', 'settlement_block_hash': 'test-block', 'model_id': 'test-model', 'compute_spend': '1.5', 'settled_at': '2026-10-10T00:00:00Z', 'source_url': 'https://flop.finance/testnet/', 'environment': 'testnet', 'simulation': False}
    def test_reject_simulations_placeholders_and_invalid_amounts(self):
        for field, value in [('simulation', True), ('session_id', 'TODO'), ('compute_spend', 'NaN'), ('compute_spend', '-1'), ('compute_spend', 'Infinity')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                tasks.validate_receipt({**self.receipt(), field: value})
    def test_receipt_signs_verifies_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            receipt = path / 'receipt.json'
            receipt.write_text(json.dumps(self.receipt()))
            with patch.object(activity, 'TESTNET_FILE', path/'testnet.jsonl'), patch.object(activity, 'ACTIVITY_FILE', path/'activity.jsonl'), patch.object(agent, '_load_seed', return_value=bytes(range(32))):
                result = tasks.record(receipt)
                self.assertFalse(result['chain_verified'])
                self.assertEqual(activity.verify_logs()['testnet_action_proofs_verified'], 1)
                with self.assertRaises(ValueError):
                    tasks.record(receipt)
                saved = json.loads((path/'testnet.jsonl').read_text())
                saved['payload']['receipt']['compute_spend'] = '1000'
                (path/'testnet.jsonl').write_text(json.dumps(saved)+'\n')
                with self.assertRaises(agent.FlopAgentError):
                    activity.verify_logs()

if __name__ == '__main__':
    unittest.main()
