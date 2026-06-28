from datetime import date
import tempfile
import unittest
from pathlib import Path

from scripts.config import AgentSelection, HarnessConfig, RuntimeConfig
from scripts.conversation import create_run_dir
from scripts.outline import StoryInput
from scripts.runner import format_book, run_book_harness, run_outline_queue


class FakeWriterClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, options, keep_alive):
        self.calls.append(messages)
        return f"draft {len(self.calls)}"


def make_config(output_dir: Path, outlines_dir: Path | None = None):
    return HarnessConfig(
        agents=AgentSelection(writer="ollama-qwen3-8b", reviewer="ollama-glm4-9b"),
        presets={
            "ollama-qwen3-8b": {
                "type": "ollama",
                "provider": "ollama",
                "model": "qwen3:8b",
            },
            "ollama-glm4-9b": {
                "type": "ollama",
                "provider": "ollama",
                "model": "glm4:9b",
            },
        },
        runtime=RuntimeConfig(rounds=1, output_dir=output_dir, outlines_dir=outlines_dir or Path("outlines")),
    )


class RunnerTest(unittest.TestCase):
    def test_create_run_dir_uses_date_and_story_title_with_suffixes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            first = create_run_dir(root, "雨季前的井", today=date(2026, 6, 28))
            second = create_run_dir(root, "雨季前的井", today=date(2026, 6, 28))

            self.assertEqual(first.name, "20260628-雨季前的井")
            self.assertEqual(second.name, "20260628-雨季前的井-1")
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_format_book_joins_title_and_chapters(self):
        book = format_book("故事", [("第一章", "內容一"), ("第二章", "內容二")])

        self.assertEqual(book, "# 故事\n\n## 第一章\n\n內容一\n\n## 第二章\n\n內容二\n")

    def test_run_book_harness_writes_chapters_and_book(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeWriterClient()
            config = make_config(Path(tmpdir))
            story_input = StoryInput(
                title="故事",
                outline="# 故事\n\n## 第一章\n\n內容一\n\n## 第二章\n\n內容二",
                target_chapter=None,
                target_chapter_title="全書",
                target_chapter_body="",
                source_path=Path("outlines/story.md"),
            )

            result = run_book_harness(story_input, config, client)

            self.assertRegex(result.run_dir.name, r"^\d{8}-故事$")
            self.assertTrue((result.run_dir / "chapters" / "chapter-01.md").exists())
            self.assertTrue((result.run_dir / "chapters" / "chapter-02.md").exists())
            self.assertIn("## 第一章", result.final_text)
            self.assertEqual(len(client.calls), 2)

    def test_run_outline_queue_marks_each_outline_done(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outlines_dir = root / "outlines"
            outlines_dir.mkdir()
            first = outlines_dir / "a.md"
            second = outlines_dir / "b.md"
            first.write_text("# 甲\n\n## 第一章\n\n內容")
            second.write_text("# 乙\n\n## 第一章\n\n內容")
            client = FakeWriterClient()
            config = make_config(root / "runs", outlines_dir=outlines_dir)

            results = run_outline_queue(config, client, client)

            self.assertEqual(len(results), 2)
            self.assertTrue(first.with_suffix(".md.done").exists())
            self.assertTrue(second.with_suffix(".md.done").exists())


if __name__ == "__main__":
    unittest.main()
