import json
import unittest

import flop_activity


class FlopActivityTests(unittest.TestCase):
    def test_initial_message_uses_only_official_sources(self):
        self.assertIn("https://flop.finance/teaser/", flop_activity.INITIAL_MESSAGE)
        self.assertIn("https://github.com/flop-labs/", flop_activity.INITIAL_MESSAGE)

    def test_source_requires_public_https_url(self):
        self.assertEqual(
            flop_activity._validate_source("https://flop.finance/teaser/"),
            "https://flop.finance/teaser/",
        )
        with self.assertRaises(Exception):
            flop_activity._validate_source("http://example.com/")
        with self.assertRaises(Exception):
            flop_activity._validate_source("https://user:pass@example.com/")

    def test_testnet_payload_has_canonical_json(self):
        payload = {"b": 2, "a": 1}
        self.assertEqual(
            json.dumps(payload, sort_keys=True, separators=(",", ":")), '{"a":1,"b":2}'
        )


if __name__ == "__main__":
    unittest.main()
