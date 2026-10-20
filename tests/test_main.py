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


def make_query() -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.message.edit_text = AsyncMock()
    query.message.edit_media = AsyncMock()
    query.message.answer_document = AsyncMock()
    return query


class TextTest(unittest.TestCase):
    def test_menu_shows_escaped_title_and_language_prompt(self):
        self.assertEqual(
            main.menu_text("A <b>&</b>"),
            f"{main.emoji('🌐')} <b>A &lt;b&gt;&amp;&lt;/b&gt;</b>\nВыберите язык субтитров:",
        )

    def test_format_picker_names_the_chosen_track(self):
        text = main.format_text("Тест", Track("ru-orig", auto=True))
        self.assertIn("Русский · авто", text)
        self.assertIn("Выберите формат файла", text)

    def test_progress_shows_step_and_track_label(self):
        text = main.progress_text("Тест", Track("ru-orig", auto=True), "Скачиваю субтитры")
        self.assertIn("Скачиваю субтитры: Русский · авто…", text)


class LanguagePressTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.videos.clear()
        self.token = main.remember(video())

    async def test_language_press_shows_format_picker_without_downloading(self):
        query = make_query()
        with patch.object(main.subtitles, "download_cues") as download:
            await main.on_track(query, main.TrackCallback(token=self.token, index=0))

        download.assert_not_called()
        text = query.message.edit_text.await_args.args[0]
        self.assertIn("Выберите формат файла", text)
        self.assertIsNotNone(query.message.edit_text.await_args.kwargs["reply_markup"])

    async def test_stale_token_gets_alert_and_no_edits(self):
        query = make_query()
        await main.on_track(query, main.TrackCallback(token="missing", index=0))
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))
        query.message.edit_text.assert_not_awaited()


class FormatPressTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.videos.clear()
        self.token = main.remember(video())

    async def test_markdown_becomes_the_file_message_without_keyboard(self):
        query = make_query()
        callback = main.FormatCallback(token=self.token, index=0, fmt="md")
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "привет")]):
            await main.on_format(query, callback)

        progress = query.message.edit_text.await_args
        self.assertIn("Скачиваю субтитры: Русский · авто…", progress.args[0])
        query.message.answer_document.assert_not_awaited()
        media = query.message.edit_media.await_args.kwargs["media"]
        self.assertEqual(media.media.filename, "Гибель Антона 2.ru.md")
        self.assertIn("Гибель Антона &lt;2&gt;", media.caption)
        self.assertIsNone(query.message.edit_media.await_args.kwargs["reply_markup"])

    async def test_text_format_has_txt_name_and_no_timecodes(self):
        query = make_query()
        callback = main.FormatCallback(token=self.token, index=1, fmt="txt")
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(65, 66, "поехали")]):
            await main.on_format(query, callback)

        media = query.message.edit_media.await_args.kwargs["media"]
        self.assertTrue(media.media.filename.endswith(".en.txt"))
        self.assertNotIn("**[", media.media.data.decode("utf-8"))
        self.assertIn("поехали", media.media.data.decode("utf-8"))

    async def test_back_returns_to_the_language_list(self):
        query = make_query()
        callback = main.FormatCallback(token=self.token, index=0, fmt="back")
        with patch.object(main.subtitles, "download_cues") as download:
            await main.on_format(query, callback)

        download.assert_not_called()
        text = query.message.edit_text.await_args.args[0]
        self.assertIn("Выберите язык субтитров", text)

    async def test_error_keeps_the_format_picker_for_a_retry(self):
        query = make_query()
        callback = main.FormatCallback(token=self.token, index=1, fmt="md")
        error = subtitles.SubtitlesError("Субтитры не найдены")
        with patch.object(main.subtitles, "download_cues", side_effect=error):
            await main.on_format(query, callback)

        query.message.edit_media.assert_not_awaited()
        last = query.message.edit_text.await_args
        self.assertIn("Субтитры не найдены", last.args[0])
        self.assertIsNotNone(last.kwargs["reply_markup"])

    async def test_if_media_cannot_be_attached_the_file_is_sent_below(self):
        query = make_query()
        query.message.edit_media.side_effect = TelegramBadRequest(method=MagicMock(), message="cannot convert")
        callback = main.FormatCallback(token=self.token, index=0, fmt="md")
        with patch.object(main.subtitles, "download_cues", return_value=[Cue(0, 1, "привет")]):
            await main.on_format(query, callback)

        query.message.answer_document.assert_awaited_once()
        last = query.message.edit_text.await_args
        self.assertIn("Отправлено: Русский · авто", last.args[0])
        self.assertIsNone(last.kwargs["reply_markup"])


if __name__ == "__main__":
    unittest.main()
