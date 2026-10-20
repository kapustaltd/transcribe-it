import asyncio
import html
import logging
import os
import re
import secrets

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import BufferedInputFile, CallbackQuery, Message
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


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        f"{emoji('🤖')} <b>Расшифровка видео в .md</b>\n\n"
        f"{emoji('🔗')} Пришлите ссылку на видео — покажу, на каких языках есть субтитры.\n"
        f"{emoji('📄')} Выберите язык, и я пришлю расшифровку в Markdown: разделы по главам видео, абзацы с таймкодами."
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
    await status.edit_text(
        f"{emoji('🌐')} <b>{html.escape(info.title)}</b>\nВыберите язык субтитров:",
        reply_markup=language_keyboard(token, info.tracks),
    )


@router.callback_query(TrackCallback.filter())
async def on_track(query: CallbackQuery, callback_data: TrackCallback) -> None:
    info = videos.get(callback_data.token)
    if info is None or callback_data.index >= len(info.tracks):
        await query.answer("Ссылка устарела, пришлите её ещё раз", show_alert=True)
        return

    track = info.tracks[callback_data.index]
    await query.answer("Готовлю расшифровку…")
    status = await query.message.answer(f"{emoji('🔎')} Скачиваю субтитры…")
    try:
        cues = await asyncio.to_thread(subtitles.download_cues, info.url, track)
    except subtitles.SubtitlesError as error:
        await status.edit_text(f"{emoji('❌')} {html.escape(str(error))}")
        return

    document = build_document(info, track, cues)
    blob = render_markdown(document)
    await status.delete()
    title = info.title[:200]
    await query.message.answer_document(
        BufferedInputFile(blob, filename=f"{file_stem(info.title)}.{track.language}.md"),
        caption=f"{emoji('✅')} {html.escape(title)} · {html.escape(track_label(track))}",
    )


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
