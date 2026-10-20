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
from transcript import build_document, render_markdown, render_text

URL_RE = re.compile(r"https?://\S+")
MAX_CACHED_VIDEOS = 200
FORMAT_BUTTONS = {"md": "📝 Markdown (.md)", "txt": "📄 Текст (.txt)"}

router = Router()
videos: dict[str, subtitles.VideoInfo] = {}


class TrackCallback(CallbackData, prefix="track"):
    token: str
    index: int


class FormatCallback(CallbackData, prefix="fmt"):
    token: str
    index: int
    fmt: str  # "md", "txt" or "back" (return to the language list)


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


def format_keyboard(token: str, index: int):
    builder = InlineKeyboardBuilder()
    for fmt, text in FORMAT_BUTTONS.items():
        builder.button(text=text, callback_data=FormatCallback(token=token, index=index, fmt=fmt))
    builder.button(text="← Назад", callback_data=FormatCallback(token=token, index=index, fmt="back"))
    builder.adjust(2, 1)
    return builder.as_markup()


def file_stem(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', " ", title).strip()
    return cleaned[:80] or "subtitles"


def menu_text(title: str) -> str:
    return f"{emoji('🌐')} <b>{html.escape(title)}</b>\nВыберите язык субтитров:"


def format_text(title: str, track: subtitles.Track) -> str:
    return (
        f"{emoji('🌐')} <b>{html.escape(title)}</b>\n"
        f"{html.escape(track_label(track))}\n"
        "Выберите формат файла:"
    )


def progress_text(title: str, track: subtitles.Track, step: str) -> str:
    return (
        f"{emoji('🌐')} <b>{html.escape(title)}</b>\n"
        f"{emoji('⏲')} {html.escape(step)}: {html.escape(track_label(track))}…"
    )


async def show_menu(menu: Message, text: str, markup=None) -> None:
    # Telegram rejects an edit that changes nothing; the menu stays as it is then.
    try:
        await menu.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass


async def show_document(menu: Message, blob: bytes, filename: str, caption: str) -> None:
    # Telegram lets a text message be replaced with a document, so the menu
    # itself becomes the file message. No keyboard: the message is final.
    await menu.edit_media(
        media=InputMediaDocument(
            media=BufferedInputFile(blob, filename=filename),
            caption=caption,
            parse_mode=ParseMode.HTML,
        ),
        reply_markup=None,
    )


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        f"{emoji('🤖')} <b>Расшифровка видео</b>\n\n"
        f"{emoji('🔗')} Пришлите ссылку на видео — покажу, на каких языках есть субтитры.\n"
        f"{emoji('📄')} Выберите язык и формат: Markdown с таймкодами или простой текст."
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
    await query.answer()
    await show_menu(
        query.message,
        format_text(info.title, track),
        format_keyboard(callback_data.token, callback_data.index),
    )


@router.callback_query(FormatCallback.filter())
async def on_format(query: CallbackQuery, callback_data: FormatCallback) -> None:
    info = videos.get(callback_data.token)
    if info is None or callback_data.index >= len(info.tracks):
        await query.answer("Ссылка устарела, пришлите её ещё раз", show_alert=True)
        return

    menu = query.message
    if callback_data.fmt == "back":
        await query.answer()
        await show_menu(menu, menu_text(info.title), language_keyboard(callback_data.token, info.tracks))
        return

    track = info.tracks[callback_data.index]
    await query.answer()
    await show_menu(menu, progress_text(info.title, track, "Скачиваю субтитры"))

    try:
        cues = await asyncio.to_thread(subtitles.download_cues, info.url, track)
    except subtitles.SubtitlesError as error:
        await show_menu(
            menu,
            f"{format_text(info.title, track)}\n{emoji('❌')} {html.escape(str(error))}",
            format_keyboard(callback_data.token, callback_data.index),
        )
        return

    document = build_document(info, cues)
    if callback_data.fmt == "txt":
        blob, extension = render_text(document), "txt"
    else:
        blob, extension = render_markdown(document), "md"
    filename = f"{file_stem(info.title)}.{track.language}.{extension}"
    caption = f"{emoji('✅')} {html.escape(info.title[:200])} · {html.escape(track_label(track))}"
    try:
        await show_document(menu, blob, filename, caption)
    except TelegramBadRequest:
        # Could not attach the file to the menu: send it below as a separate message.
        await menu.answer_document(BufferedInputFile(blob, filename=filename), caption=caption)
        await show_menu(menu, f"{emoji('🌐')} <b>{html.escape(info.title)}</b>\n{emoji('✅')} Отправлено: {html.escape(track_label(track))}")


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
