import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import main
import subtitles
from subtitles import Cue, Track, VideoInfo


def video(title="Гибель Антона <2>") -> VideoInfo:
    return VideoInfo(
        url="https://example.com/v",
        title=title,
        uploader="Кружок в круге",
        duration=268,
        chapters=(),
        tracks=(Track("ru-orig", auto=True), Track("en", auto=False)),
    )


def make_query() -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.message.edit_text = AsyncMock()
    query.message.answer_document = AsyncMock()
    return query


class MenuTextTest(unittest.TestCase):
    def test_menu_shows_escaped_title_and_prompt(self):
        self.assertEqual(
            main.menu_text("A <b>&</b>"),
            f"{main.emoji('🌐')} <b>A &lt;b&gt;&amp;&lt;/b&gt;</b>\nВыберите язык субтитров:",
        )

    def test_progress_shows_step_and_track_label(self):
        text = main.progress_text("Тест", Track("ru-orig", auto=True), "Скачиваю субтитры")
        self.assertIn("Скачиваю субтитры: Русский · авто…", text)
        self.assertIn("<b>Тест</b>", text)


class OnTrackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.videos.clear()
        self.token = main.remember(video())

    async def test_success_edits_one_message_then_sends_file_and_restores_menu(self):
        query = make_query()
        callback = main.TrackCallback(token=self.token, index=0)
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "привет")]):
            await main.on_track(query, callback)

        texts = [call.args[0] for call in query.message.edit_text.await_args_list]
        self.assertIn("Скачиваю субтитры: Русский · авто…", texts[0])
        self.assertIn("Отправлено: Русский · авто", texts[1])
        self.assertEqual(query.message.answer_document.await_count, 1)
        document = query.message.answer_document.await_args.args[0]
        self.assertTrue(document.filename.endswith(".ru.md"))
        self.assertIsNotNone(query.message.edit_text.await_args_list[1].kwargs["reply_markup"])

    async def test_error_keeps_menu_with_language_buttons(self):
        query = make_query()
        callback = main.TrackCallback(token=self.token, index=1)
        error = subtitles.SubtitlesError("Субтитры не найдены")
        with patch.object(main.subtitles, "download_cues", side_effect=error):
            await main.on_track(query, callback)

        query.message.answer_document.assert_not_awaited()
        last = query.message.edit_text.await_args_list[-1]
        self.assertIn("Субтитры не найдены", last.args[0])
        self.assertIsNotNone(last.kwargs["reply_markup"])

    async def test_stale_token_gets_alert_and_no_edits(self):
        query = make_query()
        await main.on_track(query, main.TrackCallback(token="missing", index=0))
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))
        query.message.edit_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
