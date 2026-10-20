import asyncio
import html
import logging
import os
import re
import secrets

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaDocument, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import subtitles
from premium_emoji import EMOJI, tg_emoji
from transcript import build_document, render_markdown

URL_RE = re.compile(r"https?://\S+")
MAX_CACHED_VIDEOS = 200

router = Router()
videos: dict[str, subtitles.VideoInfo] = {}


class TrackCallback(CallbackData, prefix="track"):
    token: str
    index: int


def emoji(fallback: str) -> str:
    return tg_emoji(EMOJI[fallback][0], fallback)


def remember(info: subtitles.VideoInfo) -> str:
    if len(videos) >= MAX_CACHED_VIDEOS:
        videos.pop(next(iter(videos)))
    token = secrets.token_urlsafe(6)
    videos[token] = info
    return token


def track_label(track: subtitles.Track) -> str:
    return f"{track.name} · авто" if track.auto else track.name


def language_keyboard(token: str, tracks: tuple[subtitles.Track, ...]):
    builder = InlineKeyboardBuilder()
    for index, track in enumerate(tracks):
        builder.button(text=track_label(track), callback_data=TrackCallback(token=token, index=index))
    builder.adjust(2)
    return builder.as_markup()


def file_stem(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', " ", title).strip()
    return cleaned[:80] or "subtitles"


def menu_text(title: str) -> str:
    return f"{emoji('🌐')} <b>{html.escape(title)}</b>\nВыберите язык субтитров:"


def progress_text(title: str, track: subtitles.Track, step: str) -> str:
    return (
        f"{emoji('🌐')} <b>{html.escape(title)}</b>\n"
        f"{emoji('⏲')} {html.escape(step)}: {html.escape(track_label(track))}…"
    )


async def show_menu(menu: Message, text: str, markup=None) -> None:
    # Once the menu carries the file, its text lives in the caption.
    # Telegram rejects an edit that changes nothing; the menu stays as it is then.
    try:
        if menu.document:
            await menu.edit_caption(caption=text, reply_markup=markup)
        else:
            await menu.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


async def show_document(menu: Message, blob: bytes, filename: str, caption: str, markup) -> None:
    # Telegram lets a text message be replaced with a document, so the menu
    # itself becomes the file message: caption on top, language buttons below.
    await menu.edit_media(
        media=InputMediaDocument(
            media=BufferedInputFile(blob, filename=filename),
            caption=caption,
            parse_mode=ParseMode.HTML,
        ),
        reply_markup=markup,
    )


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        f"{emoji('🤖')} <b>Расшифровка видео в .md</b>\n\n"
        f"{emoji('🔗')} Пришлите ссылку на видео — покажу, на каких языках есть субтитры.\n"
        f"{emoji('📄')} Выберите язык, и я пришлю расшифровку в Markdown: абзацы с таймкодами."
    )


@router.message(F.text)
async def on_text(message: Message) -> None:
    match = URL_RE.search(message.text)
    if match is None:
        await message.answer(f"{emoji('🔗')} Пришлите ссылку на видео.")
        return

    status = await message.answer(f"{emoji('🔎')} Ищу субтитры…")
    try:
        info = await asyncio.to_thread(subtitles.fetch_video_info, match.group(0))
    except subtitles.SubtitlesError as error:
        await status.edit_text(f"{emoji('❌')} {html.escape(str(error))}")
        return

    if not info.tracks:
        await status.edit_text(f"{emoji('❓')} У этого видео нет субтитров.")
        return

    token = remember(info)
    await status.edit_text(menu_text(info.title), reply_markup=language_keyboard(token, info.tracks))


@router.callback_query(TrackCallback.filter())
async def on_track(query: CallbackQuery, callback_data: TrackCallback) -> None:
    info = videos.get(callback_data.token)
    if info is None or callback_data.index >= len(info.tracks):
        await query.answer("Ссылка устарела, пришлите её ещё раз", show_alert=True)
        return

    track = info.tracks[callback_data.index]
    markup = language_keyboard(callback_data.token, info.tracks)
    menu = query.message
    await query.answer()
    await show_menu(menu, progress_text(info.title, track, "Скачиваю субтитры"))

    try:
        cues = await asyncio.to_thread(subtitles.download_cues, info.url, track)
    except subtitles.SubtitlesError as error:
        await show_menu(menu, f"{menu_text(info.title)}\n{emoji('❌')} {html.escape(str(error))}", markup)
        return

    blob = render_markdown(build_document(info, cues))
    filename = f"{file_stem(info.title)}.{track.language}.md"
    caption = f"{emoji('✅')} {html.escape(info.title[:200])} · {html.escape(track_label(track))}"
    try:
        await show_document(menu, blob, filename, caption, markup)
    except TelegramBadRequest:
        # Could not attach the file to the menu: send it below as a separate message.
        await menu.answer_document(BufferedInputFile(blob, filename=filename), caption=caption)
        await show_menu(menu, f"{menu_text(info.title)}\n{emoji('✅')} Отправлено: {html.escape(track_label(track))}", markup)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is not set")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
