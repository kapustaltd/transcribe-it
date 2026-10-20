import io
import unittest

from docx import Document as DocxDocument

from subtitles import Chapter, Cue, Track, VideoInfo
from transcript import (
    PARAGRAPH_SECONDS,
    PART_SECONDS,
    Document,
    Paragraph,
    Part,
    build_document,
    clock,
    paragraphs,
    render_docx,
    split_parts,
)


def info(chapters=(), duration=0.0) -> VideoInfo:
    return VideoInfo(
        url="https://example.com/v",
        title="Тестовое видео",
        uploader="Канал",
        duration=duration,
        chapters=tuple(chapters),
        tracks=(),
    )


class ClockTest(unittest.TestCase):
    def test_minutes_and_hours(self):
        self.assertEqual(clock(65.9), "01:05")
        self.assertEqual(clock(3725), "1:02:05")


class SplitPartsTest(unittest.TestCase):
    def test_uses_chapter_titles_and_puts_early_cues_into_first_chapter(self):
        chapters = (Chapter(10, 100, "Начало"), Chapter(100, 200, ""))
        cues = [Cue(2, 3, "a"), Cue(50, 51, "b"), Cue(150, 151, "c")]
        parts = split_parts(cues, chapters)
        self.assertEqual([title for title, _ in parts], ["Начало", "Глава 2"])
        self.assertEqual([cue.text for cue in parts[0][1]], ["a", "b"])
        self.assertEqual([cue.text for cue in parts[1][1]], ["c"])

    def test_without_chapters_splits_by_time_blocks(self):
        cues = [Cue(5, 6, "a"), Cue(PART_SECONDS + 1, PART_SECONDS + 2, "b")]
        parts = split_parts(cues, (), duration=PART_SECONDS * 2)
        self.assertEqual([title for title, _ in parts], ["00:00–10:00", "10:00–20:00"])
        self.assertEqual([len(group) for _, group in parts], [1, 1])

    def test_last_block_ends_at_video_duration(self):
        parts = split_parts([Cue(5, 6, "a")], (), duration=213)
        self.assertEqual([title for title, _ in parts], ["00:00–03:33"])


class ParagraphsTest(unittest.TestCase):
    def test_breaks_on_pause(self):
        cues = [Cue(0, 2, "one"), Cue(2.5, 4, "two"), Cue(8, 9, "three")]
        self.assertEqual(
            paragraphs(cues),
            (Paragraph(0, "one two"), Paragraph(8, "three")),
        )

    def test_breaks_when_paragraph_gets_too_long(self):
        cues = [Cue(index * 5, (index + 1) * 5, f"w{index}") for index in range(20)]
        result = paragraphs(cues)
        starts = [p.start for p in result]
        self.assertGreater(len(result), 1)
        self.assertTrue(all(b - a <= PARAGRAPH_SECONDS + 5 for a, b in zip(starts, starts[1:])))
        self.assertEqual(" ".join(p.text for p in result), " ".join(f"w{i}" for i in range(20)))

    def test_no_cues_give_no_paragraphs(self):
        self.assertEqual(paragraphs([]), ())


class BuildDocumentTest(unittest.TestCase):
    def test_title_facts_and_parts(self):
        track = Track("ru-orig", auto=True)
        document = build_document(
            info(duration=3725),
            track,
            [Cue(0, 1, "привет")],
        )
        self.assertEqual(document.title, "Транскрипция: Тестовое видео")
        self.assertEqual(document.source, "https://example.com/v")
        self.assertIn("Канал: Канал", document.facts)
        self.assertIn("Язык: Русский, субтитры автоматические", document.facts)
        self.assertIn("Длительность: 1:02:05", document.facts)
        self.assertEqual(document.parts, (Part("00:00–10:00", (Paragraph(0, "привет"),)),))


class RenderDocxTest(unittest.TestCase):
    def sample(self) -> Document:
        return Document(
            title="Транскрипция: Тест",
            source="https://example.com/v",
            facts=("Канал: Канал", "Язык: Русский, субтитры ручные"),
            parts=(
                Part("Начало", (Paragraph(0, "Всем привет."), Paragraph(65, "Поехали."))),
                Part("Пусто", ()),
                Part("Вторая", (Paragraph(700, "Дальше."),)),
            ),
        )

    def read(self) -> DocxDocument:
        return DocxDocument(io.BytesIO(render_docx(self.sample())))

    def test_headings_are_numbered_and_empty_parts_skipped(self):
        headings = [p.text for p in self.read().paragraphs if p.style.name == "Heading 1"]
        self.assertEqual(headings, ["Часть 1. Начало", "Часть 2. Вторая"])

    def test_timecodes_are_bold_and_text_is_plain(self):
        paragraph = next(p for p in self.read().paragraphs if "Поехали." in p.text)
        timecode, text = paragraph.runs[0], paragraph.runs[1]
        self.assertEqual(timecode.text, "[01:05] ")
        self.assertTrue(timecode.bold)
        self.assertFalse(text.bold)
        self.assertEqual(text.text, "Поехали.")

    def test_title_and_facts_are_rendered(self):
        document = self.read()
        self.assertEqual(document.paragraphs[0].text, "Транскрипция: Тест")
        meta = next(p.text for p in document.paragraphs if p.text.startswith("Канал:"))
        self.assertIn("Язык: Русский, субтитры ручные", meta)


if __name__ == "__main__":
    unittest.main()
