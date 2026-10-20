import unittest

from subtitles import Chapter, Cue, Track, chapters_from_info, parse_cues, parse_timestamp, tracks_from_info


class ParseTimestampTest(unittest.TestCase):
    def test_supports_hours_minutes_and_comma_decimal(self):
        self.assertAlmostEqual(parse_timestamp("01:02:03,500"), 3723.5)
        self.assertAlmostEqual(parse_timestamp("02:03.250"), 123.25)


class ParseCuesTest(unittest.TestCase):
    def test_reads_vtt_timings_and_strips_tags(self):
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
        self.assertEqual(
            parse_cues(raw),
            [Cue(0.0, 2.0, "hello world"), Cue(2.0, 4.0, "Tom & Jerry")],
        )

    def test_reads_srt_with_numeric_index_lines(self):
        raw = "1\n00:00:01,000 --> 00:00:02,000\n42\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond line\n"
        self.assertEqual(parse_cues(raw), [Cue(1.0, 2.0, "42"), Cue(3.0, 4.0, "Second line")])

    def test_rolling_auto_captions_keep_one_copy_and_extend_its_end(self):
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
        self.assertEqual(
            parse_cues(raw),
            [Cue(0.0, 4.0, "hello world"), Cue(2.0, 6.0, "how are you"), Cue(4.0, 6.0, "I am fine")],
        )

    def test_ignores_note_blocks_and_empty_input(self):
        raw = "WEBVTT\n\nNOTE this is a comment\n\n00:00:00.000 --> 00:00:01.000\nVisible\n"
        self.assertEqual(parse_cues(raw), [Cue(0.0, 1.0, "Visible")])
        self.assertEqual(parse_cues(""), [])


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


class ChaptersFromInfoTest(unittest.TestCase):
    def test_reads_chapters_and_skips_incomplete_ones(self):
        info = {
            "chapters": [
                {"start_time": 0, "end_time": 90.5, "title": "Вступление"},
                {"start_time": 90.5, "title": "Без конца"},
                {"start_time": 90.5, "end_time": 200, "title": ""},
            ]
        }
        self.assertEqual(
            chapters_from_info(info),
            (Chapter(0.0, 90.5, "Вступление"), Chapter(90.5, 200.0, "")),
        )

    def test_missing_chapters_give_empty_tuple(self):
        self.assertEqual(chapters_from_info({"chapters": None}), ())


class TrackNameTest(unittest.TestCase):
    def test_name_uses_base_language_of_original_track(self):
        self.assertEqual(Track("ru-orig", auto=True).name, "Русский")
        self.assertEqual(Track("ru-orig", auto=True).language, "ru")

    def test_unknown_language_falls_back_to_code(self):
        self.assertEqual(Track("sw", auto=False).name, "sw")


if __name__ == "__main__":
    unittest.main()
