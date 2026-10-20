import glob
import html
import os
import re
import tempfile
from dataclasses import dataclass

import yt_dlp
from yt_dlp.utils import YoutubeDLError

ORIGINAL_SUFFIX = "-orig"
TIMING_MARK = "-->"
TAG_RE = re.compile(r"<[^>]+>")
BLOCK_SEPARATOR_RE = re.compile(r"\n\s*\n")

LANGUAGE_NAMES = {
    "ar": "Арабский",
    "be": "Белорусский",
    "de": "Немецкий",
    "en": "Английский",
    "es": "Испанский",
    "fr": "Французский",
    "hi": "Хинди",
    "it": "Итальянский",
    "ja": "Японский",
    "kk": "Казахский",
    "ko": "Корейский",
    "nl": "Нидерландский",
    "pl": "Польский",
    "pt": "Португальский",
    "ru": "Русский",
    "tr": "Турецкий",
    "uk": "Украинский",
    "zh": "Китайский",
}


class SubtitlesError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    key: str
    auto: bool

    @property
    def language(self) -> str:
        return self.key.removesuffix(ORIGINAL_SUFFIX)

    @property
    def name(self) -> str:
        base = self.language.split("-")[0]
        return LANGUAGE_NAMES.get(base, self.language)


@dataclass(frozen=True)
class VideoInfo:
    url: str
    title: str
    tracks: tuple[Track, ...]


def _options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }


def _message(error: YoutubeDLError) -> str:
    return str(error).removeprefix("ERROR: ")


def tracks_from_info(info: dict) -> tuple[Track, ...]:
    manual = [key for key in info.get("subtitles") or {} if key != "live_chat"]
    automatic = list(info.get("automatic_captions") or {})
    originals = [key for key in automatic if key.endswith(ORIGINAL_SUFFIX)]
    return tuple(
        [Track(key, auto=False) for key in manual]
        + [Track(key, auto=True) for key in originals or automatic]
    )


def fetch_video_info(url: str) -> VideoInfo:
    try:
        with yt_dlp.YoutubeDL(_options()) as ydl:
            info = ydl.extract_info(url, download=False)
    except YoutubeDLError as error:
        raise SubtitlesError(_message(error)) from error
    return VideoInfo(
        url=url,
        title=info.get("title") or "subtitles",
        tracks=tracks_from_info(info),
    )


def subtitles_to_text(raw: str) -> str:
    lines: list[str] = []
    for block in BLOCK_SEPARATOR_RE.split(raw.replace("\r\n", "\n")):
        block_lines = block.strip().splitlines()
        timing = next((i for i, line in enumerate(block_lines) if TIMING_MARK in line), None)
        if timing is None:
            continue
        for line in block_lines[timing + 1 :]:
            text = html.unescape(TAG_RE.sub("", line)).strip()
            if text and (not lines or lines[-1] != text):
                lines.append(text)
    return "\n".join(lines)


def download_text(url: str, track: Track) -> str:
    with tempfile.TemporaryDirectory() as directory:
        options = {
            **_options(),
            "skip_download": True,
            "writesubtitles": not track.auto,
            "writeautomaticsub": track.auto,
            "subtitleslangs": [track.key],
            "subtitlesformat": "vtt/srt/best",
            "convertsubtitles": "vtt",
            "outtmpl": os.path.join(directory, "%(id)s.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except YoutubeDLError as error:
            raise SubtitlesError(_message(error)) from error

        paths = glob.glob(os.path.join(directory, "*.vtt"))
        if not paths:
            raise SubtitlesError("Не удалось скачать субтитры")
        with open(paths[0], encoding="utf-8") as file:
            text = subtitles_to_text(file.read())

    if not text:
        raise SubtitlesError("В субтитрах нет текста")
    return text
