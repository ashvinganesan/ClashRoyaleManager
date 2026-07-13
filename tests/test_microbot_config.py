import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from microbot.config import normalize_tag


class MicrobotConfigTests(unittest.TestCase):
    def test_normalize_tag(self):
        self.assertEqual(normalize_tag("abc123"), "#ABC123")
        self.assertEqual(normalize_tag("#abcO"), "#ABC0")
        self.assertIsNone(normalize_tag(""))
        self.assertIsNone(normalize_tag(None))


if __name__ == "__main__":
    unittest.main()
