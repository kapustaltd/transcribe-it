import unittest

from subtitles import Chapter, Cue, VideoInfo
from transcript import (
    PARAGRAPH_SECONDS,
    PART_SECONDS,
    Document,
    Paragraph,
    build_document,
    clock,
    escape,
    paragraphs,
    render_markdown,
    render_text,
    split_parts,
)


def info(chapters=(), duration=0.0) -> VideoInfo:
    return VideoInfo(
        url="https://example.com/v",
        title="Кремниевая долина",
        uploader="Кружок в круге",
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
    def test_groups_cues_by_chapter_and_puts_early_cues_into_first_chapter(self):
        chapters = (Chapter(10, 100, "Начало"), Chapter(100, 200, ""))
        cues = [Cue(2, 3, "a"), Cue(50, 51, "b"), Cue(150, 151, "c")]
        groups = split_parts(cues, chapters)
        self.assertEqual([[cue.text for cue in group] for group in groups], [["a", "b"], ["c"]])

    def test_without_chapters_splits_by_time_blocks(self):
        cues = [Cue(5, 6, "a"), Cue(PART_SECONDS + 1, PART_SECONDS + 2, "b")]
        groups = split_parts(cues, (), duration=PART_SECONDS * 2)
        self.assertEqual([[cue.text for cue in group] for group in groups], [["a"], ["b"]])


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
    def test_keeps_video_title_source_and_paragraphs_in_order(self):
        document = build_document(info(duration=213), [Cue(0, 1, "привет"), Cue(1.2, 2, "мир")])
        self.assertEqual(document.title, "Кремниевая долина")
        self.assertEqual(document.source, "https://example.com/v")
        self.assertEqual(document.paragraphs, (Paragraph(0, "привет мир"),))

    def test_paragraphs_of_all_parts_are_flattened(self):
        cues = [Cue(5, 6, "a"), Cue(PART_SECONDS + 1, PART_SECONDS + 2, "b")]
        document = build_document(info(duration=PART_SECONDS * 2), cues)
        self.assertEqual(document.paragraphs, (Paragraph(5, "a"), Paragraph(PART_SECONDS + 1, "b")))


class RenderMarkdownTest(unittest.TestCase):
    def sample(self) -> Document:
        return Document(
            title="Кремниевая долина",
            source="https://example.com/v",
            paragraphs=(
                Paragraph(0, "Всем привет."),
                Paragraph(65, "Поехали."),
                Paragraph(700, "Дальше *тут* звёздочки."),
            ),
        )

    def lines(self) -> list[str]:
        return render_markdown(self.sample()).decode("utf-8").splitlines()

    def test_starts_with_plain_title_and_source(self):
        self.assertEqual(self.lines()[0], "# Кремниевая долина")
        self.assertEqual(self.lines()[2], "https://example.com/v")

    def test_has_no_service_lines_or_part_headings(self):
        text = "\n".join(self.lines())
        self.assertNotIn("Транскрипция", text)
        self.assertNotIn("Канал", text)
        self.assertNotIn("Язык:", text)
        self.assertNotIn("Длительность", text)
        self.assertNotIn("## ", text)
        self.assertNotIn("Часть", text)

    def test_paragraphs_start_with_bold_timecode(self):
        self.assertIn("**[01:05]** Поехали.", self.lines())

    def test_text_is_escaped(self):
        self.assertIn("**[11:40]** Дальше \\*тут\\* звёздочки.", self.lines())

    def test_paragraphs_are_separated_by_blank_lines(self):
        self.assertIn("\n\n**[00:00]** Всем привет.\n\n**[01:05]** Поехали.\n\n", render_markdown(self.sample()).decode("utf-8"))


class RenderTextTest(unittest.TestCase):
    def test_plain_text_has_title_source_and_timed_paragraphs_without_markup(self):
        document = Document(
            title="Кремниевая долина",
            source="https://example.com/v",
            paragraphs=(Paragraph(0, "Всем привет *друзья*."), Paragraph(65, "Поехали.")),
        )
        self.assertEqual(
            render_text(document).decode("utf-8"),
            "Кремниевая долина\n\nhttps://example.com/v\n\n[00:00] Всем привет *друзья*.\n\n[01:05] Поехали.\n",
        )


if __name__ == "__main__":
    unittest.main()
