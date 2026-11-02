import unittest

from kidsstudio.owner_review_web import page


class OwnerReviewWebTests(unittest.TestCase):
    def test_mobile_form_is_read_only_except_review_record(self):
        content = page("colors-red", "test-token").decode("utf-8")
        self.assertIn('name="note"', content)
        self.assertIn('name="state"', content)
        self.assertIn('action="/review"', content)
        self.assertNotIn("publish", content.lower())
        self.assertIn("form-action 'self'", content)

    def test_local_video_player_only_when_attached(self):
        without = page("red", "token").decode("utf-8")
        with_video = page("red", "token", has_video=True).decode("utf-8")
        self.assertNotIn("<video", without)
        self.assertIn('src="/video"', with_video)
        self.assertIn("playsinline", with_video)

    def test_reject_invalid_episode_and_state(self):
        with self.assertRaises(ValueError):
            page("../escape", "token")
        with self.assertRaises(ValueError):
            page("colors-red", "token", "published")

    def test_escape_token_and_status(self):
        content = page("colors-red", '"><script>bad</script>', message="<img src=x>").decode("utf-8")
        self.assertNotIn("<script>bad</script>", content)
        self.assertNotIn("<img src=x>", content)
        self.assertIn("&lt;img", content)


if __name__ == "__main__":
    unittest.main()
