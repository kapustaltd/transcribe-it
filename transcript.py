import re
from dataclasses import dataclass

from subtitles import Chapter, Cue, Track, VideoInfo

PART_SECONDS = 600
PARAGRAPH_SECONDS = 45
PAUSE_SECONDS = 1.5

MARKDOWN_SPECIAL_RE = re.compile(r"([\\`*_\[\]<>])")


@dataclass(frozen=True)
class Paragraph:
    start: float
    text: str


@dataclass(frozen=True)
class Part:
    title: str
    paragraphs: tuple[Paragraph, ...]


@dataclass(frozen=True)
class Document:
    title: str
    source: str
    facts: tuple[str, ...]
    parts: tuple[Part, ...]


def clock(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def escape(text: str) -> str:
    return MARKDOWN_SPECIAL_RE.sub(r"\\\1", text)


def _chapter_index(moment: float, chapters: tuple[Chapter, ...]) -> int:
    index = 0
    for number, chapter in enumerate(chapters):
        if chapter.start <= moment:
            index = number
        else:
            break
    return index


def split_parts(
    cues: list[Cue],
    chapters: tuple[Chapter, ...],
    duration: float = 0.0,
) -> list[tuple[str, list[Cue]]]:
    if chapters:
        buckets: list[list[Cue]] = [[] for _ in chapters]
        for cue in cues:
            buckets[_chapter_index(cue.start, chapters)].append(cue)
        return [
            (chapter.title or f"Глава {number}", bucket)
            for number, (chapter, bucket) in enumerate(zip(chapters, buckets), start=1)
            if bucket
        ]

    buckets_by_index: dict[int, list[Cue]] = {}
    for cue in cues:
        buckets_by_index.setdefault(int(cue.start // PART_SECONDS), []).append(cue)
    parts = []
    for index in sorted(buckets_by_index):
        start = index * PART_SECONDS
        end = min(start + PART_SECONDS, duration) if duration else start + PART_SECONDS
        parts.append((f"{clock(start)}–{clock(end)}", buckets_by_index[index]))
    return parts


def paragraphs(cues: list[Cue]) -> tuple[Paragraph, ...]:
    result: list[Paragraph] = []
    words: list[str] = []
    start = previous_end = 0.0
    for cue in cues:
        if words and (cue.start - previous_end >= PAUSE_SECONDS or cue.start - start >= PARAGRAPH_SECONDS):
            result.append(Paragraph(start=start, text=" ".join(words)))
            words = []
        if not words:
            start = cue.start
        words.append(cue.text)
        previous_end = cue.end
    if words:
        result.append(Paragraph(start=start, text=" ".join(words)))
    return tuple(result)


def build_document(info: VideoInfo, track: Track, cues: list[Cue]) -> Document:
    duration = info.duration or max((cue.end for cue in cues), default=0.0)
    parts = tuple(
        Part(title=title, paragraphs=paragraphs(group))
        for title, group in split_parts(cues, info.chapters, duration)
    )
    facts = []
    if info.uploader:
        facts.append(f"Канал: {info.uploader}")
    facts.append(f"Язык: {track.name}, субтитры {'автоматические' if track.auto else 'ручные'}")
    if info.duration:
        facts.append(f"Длительность: {clock(info.duration)}")
    return Document(
        title=f"Транскрипция: {info.title}",
        source=info.url,
        facts=tuple(facts),
        parts=parts,
    )


def render_markdown(document: Document) -> bytes:
    blocks = [
        f"# {escape(document.title)}",
        document.source,
        "\n".join(f"- {escape(fact)}" for fact in document.facts),
    ]
    filled = [part for part in document.parts if part.paragraphs]
    for number, part in enumerate(filled, start=1):
        blocks.append(f"## Часть {number}. {escape(part.title)}")
        for paragraph in part.paragraphs:
            blocks.append(f"**[{clock(paragraph.start)}]** {escape(paragraph.text)}")
    return ("\n\n".join(blocks) + "\n").encode("utf-8")
