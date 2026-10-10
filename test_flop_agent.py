import base64
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import flop_agent


class FlopAgentTests(unittest.TestCase):
    def test_did_is_ed25519_did_key(self):
        did = flop_agent._did(bytes(range(32)))
        self.assertTrue(did.startswith("did:key:z6Mk"))
        self.assertEqual(len(did), 56)

    def test_signature_verifies_against_canonical_message(self):
        seed = bytes(range(32))
        text, encoded = flop_agent._sign_room(seed, "lobby", "123", "hello")
        signature = base64.urlsafe_b64decode(encoded + "==")
        Ed25519PrivateKey.from_private_bytes(seed).public_key().verify(
            signature, f"lobby|123|{text}".encode()
        )

    def test_text_sweep_matches_documented_control_replacement(self):
        self.assertEqual(flop_agent._clean_text("  hello\nworld\u200b  "), "hello world")

    def test_note_value_discards_warning_and_budget(self):
        response = (
            "!! UNTRUSTED CONTENT — warning\n\n"
            "did:key:z6MkExample purpose:test\n"
            "# budget: 2 of 10 reads left this minute\n"
        )
        self.assertEqual(
            flop_agent._note_value(response), "did:key:z6MkExample purpose:test"
        )

    def test_initialize_uses_private_permissions_and_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.multiple(
                flop_agent,
                PRIVATE_DIR=root / ".private",
                SEED_FILE=root / ".private" / "identity.seed",
                PUBLIC_IDENTITY_FILE=root / "identity.json",
            ):
                first = flop_agent.initialize()
                second = flop_agent.initialize()
                self.assertEqual(first["did"], second["did"])
                self.assertEqual(first["status"], "new")
                self.assertEqual(second["status"], "existing")
                mode = stat.S_IMODE((root / ".private" / "identity.seed").stat().st_mode)
                self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
