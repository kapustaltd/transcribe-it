import re
from dataclasses import dataclass

from subtitles import Chapter, Cue, VideoInfo

PART_SECONDS = 600
PARAGRAPH_SECONDS = 45
PAUSE_SECONDS = 1.5

MARKDOWN_SPECIAL_RE = re.compile(r"([\\`*_\[\]<>])")


@dataclass(frozen=True)
class Paragraph:
    start: float
    text: str


@dataclass(frozen=True)
class Document:
    title: str
    source: str
    paragraphs: tuple[Paragraph, ...]


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
) -> list[list[Cue]]:
    if chapters:
        buckets: list[list[Cue]] = [[] for _ in chapters]
        for cue in cues:
            buckets[_chapter_index(cue.start, chapters)].append(cue)
        return [bucket for bucket in buckets if bucket]

    buckets_by_index: dict[int, list[Cue]] = {}
    for cue in cues:
        buckets_by_index.setdefault(int(cue.start // PART_SECONDS), []).append(cue)
    return [buckets_by_index[index] for index in sorted(buckets_by_index)]


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


def build_document(info: VideoInfo, cues: list[Cue]) -> Document:
    duration = info.duration or max((cue.end for cue in cues), default=0.0)
    result: list[Paragraph] = []
    for group in split_parts(cues, info.chapters, duration):
        result.extend(paragraphs(group))
    return Document(title=info.title, source=info.url, paragraphs=tuple(result))


def render_markdown(document: Document) -> bytes:
    blocks = [f"# {escape(document.title)}", document.source]
    for paragraph in document.paragraphs:
        blocks.append(f"**[{clock(paragraph.start)}]** {escape(paragraph.text)}")
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def render_text(document: Document) -> bytes:
    """Plain text: title, source and one timed paragraph per block, without markup."""
    blocks = [document.title, document.source]
    blocks.extend(f"[{clock(paragraph.start)}] {paragraph.text}" for paragraph in document.paragraphs)
    return ("\n\n".join(blocks) + "\n").encode("utf-8")
