import tempfile
import unittest
from pathlib import Path

from scripts.prepare_outline import prepare_outline


class FakeOutlineClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, model, messages, options, keep_alive):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "options": options,
                "keep_alive": keep_alive,
            }
        )
        return self.response


class PrepareOutlineTest(unittest.TestCase):
    def test_prepare_outline_writes_valid_outline_named_from_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.md"
            source.write_text("一口雨季前會敲門的井。")
            prompt = root / "outline-prompt.md"
            prompt.write_text("整理成標準大綱。")
            outlines_dir = root / "outlines"
            client = FakeOutlineClient("# 雨季前的井\n\n## 第一章：井聲\n\n內容")

            output = prepare_outline(
                source_path=source,
                prompt_path=prompt,
                outlines_dir=outlines_dir,
                client=client,
                model="detected-model",
            )

            self.assertEqual(output.name, "雨季前的井.md")
            self.assertEqual(output.read_text(), "# 雨季前的井\n\n## 第一章：井聲\n\n內容\n")
            self.assertIn("一口雨季前會敲門的井。", client.calls[0]["messages"][1]["content"])

    def test_prepare_outline_can_update_source_outline_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "outlines" / "example.md"
            source.parent.mkdir()
            source.write_text("還沒整理好的大綱")
            prompt = root / "outline-prompt.md"
            prompt.write_text("整理成標準大綱。")
            client = FakeOutlineClient("# 雨季前的井\n\n## 第一章：井聲\n\n內容")

            output = prepare_outline(
                source_path=source,
                prompt_path=prompt,
                outlines_dir=source.parent,
                client=client,
                model="detected-model",
                in_place=True,
            )

            self.assertEqual(output, source)
            self.assertEqual(source.read_text(), "# 雨季前的井\n\n## 第一章：井聲\n\n內容\n")

    def test_prepare_outline_adds_suffix_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.md"
            source.write_text("素材")
            prompt = root / "outline-prompt.md"
            prompt.write_text("整理成標準大綱。")
            outlines_dir = root / "outlines"
            outlines_dir.mkdir()
            (outlines_dir / "雨季前的井.md").write_text("old")
            client = FakeOutlineClient("# 雨季前的井\n\n## 第一章：井聲\n\n內容")

            output = prepare_outline(source, prompt, outlines_dir, client, "model")

            self.assertEqual(output.name, "雨季前的井-1.md")

    def test_prepare_outline_rejects_invalid_outline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.md"
            source.write_text("素材")
            prompt = root / "outline-prompt.md"
            prompt.write_text("整理成標準大綱。")
            client = FakeOutlineClient("沒有標題")

            with self.assertRaises(ValueError):
                prepare_outline(source, prompt, root / "outlines", client, "model")


if __name__ == "__main__":
    unittest.main()
