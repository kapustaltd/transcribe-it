import glob
import html
import os
import re
import tempfile
from dataclasses import dataclass, replace

import yt_dlp
from yt_dlp.utils import YoutubeDLError

ORIGINAL_SUFFIX = "-orig"
TIMING_RE = re.compile(r"((?:\d+:)?\d+:\d{2}[.,]\d{3})\s*-->\s*((?:\d+:)?\d+:\d{2}[.,]\d{3})")
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
class Chapter:
    start: float
    end: float
    title: str


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class VideoInfo:
    url: str
    title: str
    uploader: str
    duration: float
    chapters: tuple[Chapter, ...]
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


def chapters_from_info(info: dict) -> tuple[Chapter, ...]:
    return tuple(
        Chapter(start=float(item["start_time"]), end=float(item["end_time"]), title=item.get("title") or "")
        for item in info.get("chapters") or []
        if item.get("start_time") is not None and item.get("end_time") is not None
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
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=float(info.get("duration") or 0),
        chapters=chapters_from_info(info),
        tracks=tracks_from_info(info),
    )


def parse_timestamp(value: str) -> float:
    seconds = 0.0
    for part in value.replace(",", ".").split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def parse_cues(raw: str) -> list[Cue]:
    cues: list[Cue] = []
    for block in BLOCK_SEPARATOR_RE.split(raw.replace("\r\n", "\n")):
        lines = block.strip().splitlines()
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        match = TIMING_RE.search(lines[timing])
        if match is None:
            continue
        start, end = parse_timestamp(match.group(1)), parse_timestamp(match.group(2))
        for line in lines[timing + 1 :]:
            text = html.unescape(TAG_RE.sub("", line)).strip()
            if not text:
                continue
            # YouTube auto-captions repeat the previous line in the next cue; keep one copy
            if cues and cues[-1].text == text:
                cues[-1] = replace(cues[-1], end=max(cues[-1].end, end))
                continue
            cues.append(Cue(start=start, end=end, text=text))
    return cues


def download_cues(url: str, track: Track) -> list[Cue]:
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
            cues = parse_cues(file.read())

    if not cues:
        raise SubtitlesError("В субтитрах нет текста")
    return cues
