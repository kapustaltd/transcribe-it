import unittest

from subtitles import Chapter, Cue, Track, VideoInfo
from transcript import (
    PARAGRAPH_SECONDS,
    PART_SECONDS,
    Document,
    Paragraph,
    Part,
    build_document,
    clock,
    escape,
    paragraphs,
    render_markdown,
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


class EscapeTest(unittest.TestCase):
    def test_escapes_markdown_special_characters(self):
        self.assertEqual(escape("*жирный* _курсив_ [ссылка](url)"), "\\*жирный\\* \\_курсив\\_ \\[ссылка\\](url)")

    def test_plain_text_is_unchanged(self):
        self.assertEqual(escape("Обычный текст, без разметки."), "Обычный текст, без разметки.")


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
        document = build_document(info(duration=3725), track, [Cue(0, 1, "привет")])
        self.assertEqual(document.title, "Транскрипция: Тестовое видео")
        self.assertEqual(document.source, "https://example.com/v")
        self.assertIn("Канал: Канал", document.facts)
        self.assertIn("Язык: Русский, субтитры автоматические", document.facts)
        self.assertIn("Длительность: 1:02:05", document.facts)
        self.assertEqual(document.parts, (Part("00:00–10:00", (Paragraph(0, "привет"),)),))


class RenderMarkdownTest(unittest.TestCase):
    def sample(self) -> Document:
        return Document(
            title="Транскрипция: Тест",
            source="https://example.com/v",
            facts=("Канал: Канал", "Язык: Русский, субтитры ручные"),
            parts=(
                Part("Начало", (Paragraph(0, "Всем привет."), Paragraph(65, "Поехали."))),
                Part("Пусто", ()),
                Part("Вторая", (Paragraph(700, "Дальше *тут* звёздочки."),)),
            ),
        )

    def text(self) -> str:
        return render_markdown(self.sample()).decode("utf-8")

    def test_title_source_and_facts_come_first(self):
        lines = self.text().splitlines()
        self.assertEqual(lines[0], "# Транскрипция: Тест")
        self.assertEqual(lines[2], "https://example.com/v")
        self.assertIn("- Канал: Канал", lines)
        self.assertIn("- Язык: Русский, субтитры ручные", lines)

    def test_headings_are_numbered_and_empty_parts_skipped(self):
        headings = [line for line in self.text().splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## Часть 1. Начало", "## Часть 2. Вторая"])

    def test_paragraphs_start_with_bold_timecode(self):
        self.assertIn("**[01:05]** Поехали.", self.text().splitlines())

    def test_text_is_escaped(self):
        self.assertIn("**[11:40]** Дальше \\*тут\\* звёздочки.", self.text().splitlines())

    def test_paragraphs_are_separated_by_blank_lines(self):
        self.assertIn("\n\n**[00:00]** Всем привет.\n\n**[01:05]** Поехали.\n\n", self.text())


if __name__ == "__main__":
    unittest.main()
