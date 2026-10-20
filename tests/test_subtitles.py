import unittest

from subtitles import Track, subtitles_to_text, tracks_from_info


class SubtitlesToTextTest(unittest.TestCase):
    def test_strips_webvtt_header_timings_and_tags(self):
        raw = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: en\n"
            "\n"
            "00:00:00.000 --> 00:00:02.000 align:start position:0%\n"
            "hello<00:00:00.500><c> world</c>\n"
            "\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "Tom &amp; Jerry\n"
        )
        self.assertEqual(subtitles_to_text(raw), "hello world\nTom & Jerry")

    def test_parses_srt_and_skips_numeric_index_lines(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n42\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond line\n"
        self.assertEqual(subtitles_to_text(raw), "42\nSecond line")

    def test_drops_consecutive_duplicates_from_rolling_auto_captions(self):
        raw = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "hello world\n\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "hello world\n"
            "how are you\n\n"
            "00:00:04.000 --> 00:00:06.000\n"
            "how are you\n"
            "I am fine\n"
        )
        self.assertEqual(subtitles_to_text(raw), "hello world\nhow are you\nI am fine")

    def test_ignores_note_blocks_and_empty_input(self):
        raw = "WEBVTT\n\nNOTE this is a comment\n\n00:00:00.000 --> 00:00:01.000\nVisible\n"
        self.assertEqual(subtitles_to_text(raw), "Visible")
        self.assertEqual(subtitles_to_text(""), "")


class TracksFromInfoTest(unittest.TestCase):
    def test_manual_tracks_come_first_and_live_chat_is_skipped(self):
        info = {
            "subtitles": {"en": [{}], "live_chat": [{}]},
            "automatic_captions": {"ru-orig": [{}], "en": [{}]},
        }
        self.assertEqual(
            tracks_from_info(info),
            (Track("en", auto=False), Track("ru-orig", auto=True)),
        )

    def test_auto_captions_keep_only_original_language_when_present(self):
        info = {"subtitles": {}, "automatic_captions": {"ru-orig": [{}], "fr": [{}], "de": [{}]}}
        self.assertEqual(tracks_from_info(info), (Track("ru-orig", auto=True),))

    def test_auto_captions_fall_back_to_all_keys_without_original(self):
        info = {"automatic_captions": {"en": [{}], "de": [{}]}}
        self.assertEqual(tracks_from_info(info), (Track("en", auto=True), Track("de", auto=True)))

    def test_no_subtitles_gives_no_tracks(self):
        self.assertEqual(tracks_from_info({}), ())


class TrackNameTest(unittest.TestCase):
    def test_name_uses_base_language_of_original_track(self):
        self.assertEqual(Track("ru-orig", auto=True).name, "Русский")
        self.assertEqual(Track("ru-orig", auto=True).language, "ru")

    def test_unknown_language_falls_back_to_code(self):
        self.assertEqual(Track("sw", auto=False).name, "sw")


if __name__ == "__main__":
    unittest.main()
