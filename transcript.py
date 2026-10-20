import io
from dataclasses import dataclass

from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor

from subtitles import Chapter, Cue, Track, VideoInfo

PART_SECONDS = 600
PARAGRAPH_SECONDS = 45
PAUSE_SECONDS = 1.5

TITLE_COLOR = RGBColor(0x1B, 0x36, 0x5D)
TEXT_COLOR = RGBColor(0x22, 0x22, 0x22)
MUTED_COLOR = RGBColor(0x55, 0x55, 0x55)


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


def render_docx(document: Document) -> bytes:
    docx = DocxDocument()
    normal = docx.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = TEXT_COLOR
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15

    title = docx.add_paragraph()
    title.paragraph_format.space_after = Pt(2)
    run = title.add_run(document.title)
    run.bold = True
    run.font.size = Pt(22)
    run.font.color.rgb = TITLE_COLOR
    docx.core_properties.title = document.title

    source = docx.add_paragraph()
    source.paragraph_format.space_after = Pt(18)
    run = source.add_run(document.source)
    run.italic = True
    run.font.size = Pt(13)
    run.font.color.rgb = MUTED_COLOR

    if document.facts:
        meta = docx.add_paragraph()
        meta.paragraph_format.left_indent = Pt(14.4)
        meta.paragraph_format.space_after = Pt(20)
        for index, fact in enumerate(document.facts):
            run = meta.add_run(fact)
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
            if index < len(document.facts) - 1:
                run.add_break()

    filled = [part for part in document.parts if part.paragraphs]
    for number, part in enumerate(filled, start=1):
        heading = docx.add_heading(level=1)
        heading.paragraph_format.space_before = Pt(16)
        heading.paragraph_format.space_after = Pt(8)
        heading.paragraph_format.keep_with_next = True
        run = heading.add_run(f"Часть {number}. {part.title}")
        run.bold = True
        run.font.name = "Calibri"
        run.font.size = Pt(16)
        run.font.color.rgb = TITLE_COLOR

        for paragraph in part.paragraphs:
            body = docx.add_paragraph()
            timecode = body.add_run(f"[{clock(paragraph.start)}] ")
            timecode.bold = True
            timecode.font.color.rgb = MUTED_COLOR
            body.add_run(paragraph.text)

    buffer = io.BytesIO()
    docx.save(buffer)
    return buffer.getvalue()
