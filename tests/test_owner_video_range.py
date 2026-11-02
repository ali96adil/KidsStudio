import unittest

from kidsstudio.owner_video_range import parse_range, MAX_CHUNK


class VideoRangeTests(unittest.TestCase):
    def test_regular_range(self):
        self.assertEqual(parse_range("bytes=2-5", 100), (2, 5, True))

    def test_open_range(self):
        self.assertEqual(parse_range("bytes=95-", 100), (95, 99, True))

    def test_suffix_range(self):
        self.assertEqual(parse_range("bytes=-3", 100), (97, 99, True))

    def test_default_small_file(self):
        self.assertEqual(parse_range(None, 100), (0, 99, False))

    def test_default_large_file_is_bounded(self):
        self.assertEqual(parse_range(None, MAX_CHUNK + 5), (0, MAX_CHUNK - 1, True))

    def test_reject_invalid(self):
        for header in ("bytes=100-200", "bytes=5-2", "bytes=0-1,3-4", "bytes=-0", "other=0-2", "bytes=-"):
            with self.subTest(header=header):
                with self.assertRaises(ValueError):
                    parse_range(header, 100)


if __name__ == "__main__":
    unittest.main()
