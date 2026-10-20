import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest

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


def make_query(document=None) -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.message.document = document
    query.message.edit_text = AsyncMock()
    query.message.edit_caption = AsyncMock()
    query.message.edit_media = AsyncMock()
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

    async def test_success_turns_the_menu_message_into_the_file(self):
        query = make_query()
        callback = main.TrackCallback(token=self.token, index=0)
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "привет")]):
            await main.on_track(query, callback)

        progress = query.message.edit_text.await_args
        self.assertIn("Скачиваю субтитры: Русский · авто…", progress.args[0])
        self.assertIsNone(progress.kwargs["reply_markup"])

        query.message.answer_document.assert_not_awaited()
        media = query.message.edit_media.await_args.kwargs["media"]
        self.assertEqual(media.media.filename, "Гибель Антона 2.ru.md")
        self.assertIn("Гибель Антона &lt;2&gt;", media.caption)
        self.assertIn("Русский · авто", media.caption)
        self.assertIsNone(query.message.edit_media.await_args.kwargs["reply_markup"])

    async def test_second_pick_on_a_file_message_edits_its_caption_first(self):
        query = make_query(document=MagicMock())
        callback = main.TrackCallback(token=self.token, index=1)
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "hello")]):
            await main.on_track(query, callback)

        self.assertIn("Скачиваю субтитры: Английский…", query.message.edit_caption.await_args_list[0].kwargs["caption"])
        query.message.edit_text.assert_not_awaited()
        self.assertTrue(query.message.edit_media.await_args.kwargs["media"].media.filename.endswith(".en.md"))

    async def test_if_media_cannot_be_attached_the_file_is_sent_below_the_menu(self):
        query = make_query()
        query.message.edit_media.side_effect = TelegramBadRequest(method=MagicMock(), message="cannot convert")
        callback = main.TrackCallback(token=self.token, index=0)
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "привет")]):
            await main.on_track(query, callback)

        query.message.answer_document.assert_awaited_once()
        last = query.message.edit_text.await_args_list[-1]
        self.assertIn("Отправлено: Русский · авто", last.args[0])
        self.assertIsNone(last.kwargs["reply_markup"])

    async def test_error_keeps_menu_with_language_buttons(self):
        query = make_query()
        callback = main.TrackCallback(token=self.token, index=1)
        error = subtitles.SubtitlesError("Субтитры не найдены")
        with patch.object(main.subtitles, "download_cues", side_effect=error):
            await main.on_track(query, callback)

        query.message.edit_media.assert_not_awaited()
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
