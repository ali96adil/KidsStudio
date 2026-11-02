import unittest

from kidsstudio.owner_review_access import authorize_bearer, new_token


class ReviewAccessTests(unittest.TestCase):
    def test_authorize_correct_token(self):
        token = new_token()
        self.assertTrue(authorize_bearer("Bearer " + token, token))

    def test_reject_wrong_and_missing_token(self):
        token = new_token()
        self.assertFalse(authorize_bearer(None, token))
        self.assertFalse(authorize_bearer("Basic " + token, token))
        self.assertFalse(authorize_bearer("Bearer " + new_token(), token))
        self.assertFalse(authorize_bearer("Bearer " + ("x" * 513), token))

    def test_reject_short_secret(self):
        with self.assertRaises(ValueError):
            authorize_bearer("Bearer abc", "abc")


if __name__ == "__main__":
    unittest.main()
