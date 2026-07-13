import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ClashRoyaleManager"))

from utils.verification_utils import VERIFICATION_CODE_LENGTH, VERIFICATION_CODE_PREFIX, generate_verification_code


class VerificationUtilsTests(unittest.TestCase):
    def test_generate_verification_code_shape(self):
        code = generate_verification_code()

        self.assertTrue(code.startswith(f"{VERIFICATION_CODE_PREFIX}-"))
        self.assertEqual(len(code), len(VERIFICATION_CODE_PREFIX) + 1 + VERIFICATION_CODE_LENGTH)
        self.assertTrue(code.split("-", 1)[1].isalnum())
        self.assertEqual(code, code.upper())


if __name__ == "__main__":
    unittest.main()
