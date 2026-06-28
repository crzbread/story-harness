import tempfile
import sys
import unittest
from pathlib import Path

from story_harness import (
    CommandClient,
    AgentSelection,
    HarnessConfig,
    RuntimeConfig,
    StoryInput,
    clean_story_output,
    create_client,
    get_agent_preset,
    load_config,
    load_prompt,
    load_story_input,
    mark_outline_done,
    runtime_summary,
    run_book_harness,
    run_harness,
    run_outline_queue,
)


class FakeOllamaClient:
    def __init__(self):
        self.calls = []
        self.writer_calls = 0
        self.reviewer_calls = 0

    def chat(self, model, messages, options, keep_alive):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "options": options,
                "keep_alive": keep_alive,
            }
        )
        if "請審稿" in messages[1]["content"]:
            self.reviewer_calls += 1
            return f"review {self.reviewer_calls}"
        self.writer_calls += 1
        return f"draft {self.writer_calls}"


def make_config(rounds=3, output_dir=Path("runs"), agents=None, presets=None):
    return HarnessConfig(
        agents=agents or AgentSelection(writer="ollama-qwen3-8b", reviewer="ollama-glm4-9b"),
        presets=presets
        or {
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
        runtime=RuntimeConfig(rounds=rounds, output_dir=output_dir),
    )


class StoryHarnessTest(unittest.TestCase):
    def test_load_config_reads_agent_presets_and_runtime_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                """{
  "agents": {
    "writer": "ollama-qwen3",
    "reviewer": "ollama-glm4"
  },
  "_available_presets": ["ollama-glm4", "ollama-qwen3"],
  "runtime": {
    "rounds": 2,
    "num_ctx": 1024,
    "num_predict": 500
  }
}
"""
            )
            (Path(tmpdir) / "presets.generated.json").write_text(
                """{
  "ollama-qwen3": {
    "type": "ollama",
    "provider": "ollama",
    "model": "qwen3:8b"
  },
  "ollama-glm4": {
    "type": "ollama",
    "provider": "ollama",
    "model": "glm4:9b"
  }
}
"""
            )

            config = load_config(config_path)

            self.assertEqual(config.agents.writer, "ollama-qwen3")
            self.assertEqual(config.agents.reviewer, "ollama-glm4")
            self.assertEqual(get_agent_preset(config, "writer")["model"], "qwen3:8b")
            self.assertEqual(get_agent_preset(config, "reviewer")["model"], "glm4:9b")
            self.assertEqual(config.runtime.rounds, 2)
            self.assertEqual(config.runtime.num_ctx, 1024)
            self.assertEqual(config.runtime.num_predict, 500)

    def test_load_config_reads_agent_providers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                """{
  "agents": {
    "writer": "claude-sonnet-thinking",
    "reviewer": "ollama-glm4"
  }
}
"""
            )
            (Path(tmpdir) / "presets.generated.json").write_text(
                """{
  "claude-sonnet-thinking": {
    "type": "command",
    "provider": "agy",
    "model": "Claude Sonnet 4.6 (Thinking)",
    "command": ["claude", "-p", "{prompt}"]
  },
  "ollama-glm4": {
    "type": "ollama",
    "model": "glm4:9b"
  }
}
"""
            )

            config = load_config(config_path)

            self.assertEqual(config.agents.writer, "claude-sonnet-thinking")
            self.assertEqual(config.agents.reviewer, "ollama-glm4")
            self.assertEqual(get_agent_preset(config, "writer")["provider"], "agy")
            self.assertEqual(get_agent_preset(config, "reviewer")["type"], "ollama")
            self.assertEqual(get_agent_preset(config, "reviewer")["model"], "glm4:9b")
            self.assertEqual(
                config.presets["claude-sonnet-thinking"]["model"],
                "Claude Sonnet 4.6 (Thinking)",
            )

    def test_create_client_builds_command_provider(self):
        config = HarnessConfig(
            agents=AgentSelection(writer="claude-sonnet-thinking"),
            presets={
                "claude-sonnet-thinking": {
                    "type": "command",
                    "provider": "agy",
                    "command": ["claude", "-p", "{prompt}"],
                }
            },
        )

        client = create_client(config, "writer")

        self.assertIsInstance(client, CommandClient)

    def test_command_provider_timeout_raises_runtime_error(self):
        client = CommandClient(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            timeout=0.01,
        )

        with self.assertRaises(RuntimeError) as error:
            client.chat("", [{"role": "user", "content": "hello"}], {}, "")

        self.assertIn("命令列 agent 執行超時", str(error.exception))

    def test_load_prompt_requires_prompt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "missing.md"

            with self.assertRaises(FileNotFoundError) as error:
                load_prompt(prompt_path)

            self.assertIn("Prompt file not found", str(error.exception))

    def test_runtime_summary_omits_ollama_memory_settings_for_command_only_agents(self):
        config = HarnessConfig(
            agents=AgentSelection(
                writer="agy-claude-sonnet",
                reviewer="agy-gemini-flash",
            ),
            presets={
                "agy-claude-sonnet": {
                    "type": "command",
                    "provider": "agy",
                    "model": "Claude Sonnet",
                    "command": ["agy", "-p", "{prompt}"],
                    "timeout": 1800,
                },
                "agy-gemini-flash": {
                    "type": "command",
                    "provider": "agy",
                    "model": "Gemini Flash",
                    "command": ["agy", "-p", "{prompt}"],
                    "timeout": 1200,
                },
            },
        )

        summary = runtime_summary(config)

        self.assertNotIn("Memory guard", summary)
        self.assertNotIn("num_ctx", summary)
        self.assertIn("Command providers", summary)
        self.assertIn("timeout=1800s", summary)

    def test_load_story_input_reads_outline_and_selects_chapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outlines_dir = Path(tmpdir) / "outlines"
            outlines_dir.mkdir()
            (outlines_dir / "outline.md").write_text(
                """# 最後一封無人寄出的信

## 第一章：舊屋裡的信箱

主角回到老屋。

## 第二章：不存在的地址

主角前往小鎮。
"""
            )

            story_input = load_story_input(outlines_dir, None, 2)

            self.assertEqual(story_input.title, "最後一封無人寄出的信")
            self.assertIn("## 第一章：舊屋裡的信箱", story_input.outline)
            self.assertEqual(story_input.target_chapter_title, "第二章：不存在的地址")
            self.assertEqual(story_input.target_chapter_body, "主角前往小鎮。")

    def test_load_story_input_rejects_noncanonical_outline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outlines_dir = Path(tmpdir) / "outlines"
            outlines_dir.mkdir()
            (outlines_dir / "outline.md").write_text(
                """## 1.《不合規標題》

### 第一章：錯誤章節層級

內容
"""
            )

            with self.assertRaises(ValueError) as error:
                load_story_input(outlines_dir, None, None)

            self.assertIn("大綱格式錯誤", str(error.exception))

    def test_load_story_input_skips_done_outlines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outlines_dir = Path(tmpdir) / "outlines"
            outlines_dir.mkdir()
            first = outlines_dir / "a.md"
            second = outlines_dir / "b.md"
            first.write_text("# 已完成\n\n## 第一章：開始\n\n完成")
            second.write_text("# 待執行\n\n## 第一章：開始\n\n待執行")
            mark_outline_done(first)

            story_input = load_story_input(outlines_dir, None, None)

            self.assertEqual(story_input.source_path, second)
            self.assertEqual(story_input.title, "待執行")

    def test_run_outline_queue_processes_all_pending_outlines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outlines_dir = root / "outlines"
            output_dir = root / "runs"
            outlines_dir.mkdir()
            first = outlines_dir / "a.md"
            second = outlines_dir / "b.md"
            first.write_text("# 第一個故事\n\n## 第一章：開始\n\n內容")
            second.write_text("# 第二個故事\n\n## 第一章：開始\n\n內容")
            config = make_config(rounds=1, output_dir=output_dir)
            config = HarnessConfig(
                agents=config.agents,
                presets=config.presets,
                runtime=RuntimeConfig(
                    rounds=config.runtime.rounds,
                    output_dir=config.runtime.output_dir,
                    outlines_dir=outlines_dir,
                ),
            )
            client = FakeOllamaClient()

            results = run_outline_queue(config, client, client)

            self.assertEqual(len(results), 2)
            self.assertTrue(first.with_suffix(".md.done").exists())
            self.assertTrue(second.with_suffix(".md.done").exists())
            self.assertEqual(client.writer_calls, 2)

    def test_runs_three_writer_reviewer_rounds_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeOllamaClient()
            config = make_config(rounds=3, output_dir=Path(tmpdir))
            events = []

            story_input = StoryInput(
                title="短篇故事",
                outline="# 短篇故事\n\n## 第 1 章：開始\n\n寫一個短篇故事",
                target_chapter=1,
                target_chapter_title="第 1 章：開始",
                target_chapter_body="寫一個短篇故事",
                source_path=Path("outlines/test.md"),
            )

            result = run_harness(story_input, config, client, progress=events.append)

            self.assertEqual(result.final_text, "draft 3")
            self.assertEqual(len(client.calls), 5)
            self.assertEqual(
                [call["model"] for call in client.calls],
                [
                    "qwen3:8b",
                    "glm4:9b",
                    "qwen3:8b",
                    "glm4:9b",
                    "qwen3:8b",
                ],
            )
            self.assertTrue(all(call["keep_alive"] == "0s" for call in client.calls))
            self.assertTrue((result.run_dir / "round-01-draft.md").exists())
            self.assertTrue((result.run_dir / "round-01-review.md").exists())
            target_text = (result.run_dir / "target.md").read_text()
            self.assertIn("# 寫作目標", target_text)
            self.assertIn("## 本章大綱", target_text)
            self.assertIn("故事題目：短篇故事", target_text)
            self.assertEqual((result.run_dir / "final.md").read_text(), "draft 3\n")
            self.assertEqual(
                events,
                [
                    "round 1/3 writer start: qwen3:8b",
                    "round 1/3 writer done",
                    "round 1/3 reviewer start: glm4:9b",
                    "round 1/3 reviewer done",
                    "round 2/3 writer start: qwen3:8b",
                    "round 2/3 writer done",
                    "round 2/3 reviewer start: glm4:9b",
                    "round 2/3 reviewer done",
                    "round 3/3 writer start: qwen3:8b",
                    "round 3/3 writer done",
                ],
            )

    def test_run_harness_validates_prompts_before_creating_run_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "runs"
            config = make_config(rounds=1, output_dir=output_dir)
            config = HarnessConfig(
                agents=config.agents,
                presets=config.presets,
                runtime=RuntimeConfig(
                    rounds=config.runtime.rounds,
                    output_dir=config.runtime.output_dir,
                    writer_prompt_path=Path(tmpdir) / "missing-writer.md",
                    reviewer_prompt_path=Path(tmpdir) / "missing-reviewer.md",
                ),
            )
            story_input = StoryInput(
                title="短篇故事",
                outline="# 短篇故事\n\n## 第 1 章：開始\n\n寫一個短篇故事",
                target_chapter=1,
                target_chapter_title="第 1 章：開始",
                target_chapter_body="寫一個短篇故事",
                source_path=Path("outlines/test.md"),
            )

            with self.assertRaises(FileNotFoundError):
                run_harness(story_input, config, FakeOllamaClient())

            self.assertFalse(output_dir.exists())

    def test_run_book_harness_writes_each_chapter_and_final_book(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeOllamaClient()
            config = make_config(rounds=1, output_dir=Path(tmpdir))
            story_input = StoryInput(
                title="最後一封無人寄出的信",
                outline=(
                    "# 最後一封無人寄出的信\n\n"
                    "## 第一章：舊屋裡的信箱\n\n"
                    "主角回到老屋。\n\n"
                    "## 第二章：不存在的地址\n\n"
                    "主角前往小鎮。"
                ),
                target_chapter=None,
                target_chapter_title="全書",
                target_chapter_body="",
                source_path=Path("outlines/test.md"),
            )

            result = run_book_harness(story_input, config, client)

            self.assertTrue((result.run_dir / "chapters" / "chapter-01.md").exists())
            self.assertTrue((result.run_dir / "chapters" / "chapter-02.md").exists())
            final_book = (result.run_dir / "book.md").read_text()
            self.assertIn("# 最後一封無人寄出的信", final_book)
            self.assertIn("## 第一章：舊屋裡的信箱", final_book)
            self.assertIn("## 第二章：不存在的地址", final_book)
            self.assertEqual(client.writer_calls, 2)
            self.assertEqual(client.reviewer_calls, 0)

    def test_later_chapters_receive_previous_completed_chapters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeOllamaClient()
            config = make_config(rounds=1, output_dir=Path(tmpdir))
            story_input = StoryInput(
                title="最後一封無人寄出的信",
                outline=(
                    "# 最後一封無人寄出的信\n\n"
                    "## 第一章：舊屋裡的信箱\n\n"
                    "主角回到老屋。\n\n"
                    "## 第二章：不存在的地址\n\n"
                    "主角前往小鎮。"
                ),
                target_chapter=None,
                target_chapter_title="全書",
                target_chapter_body="",
                source_path=Path("outlines/test.md"),
            )

            run_book_harness(story_input, config, client)

            second_writer_call = client.calls[1]
            self.assertIn("<已完成前文>", second_writer_call["messages"][1]["content"])
            self.assertIn("draft 1", second_writer_call["messages"][1]["content"])

    def test_clean_story_output_removes_review_contamination(self):
        dirty = """橘貓夜遊

小偵拆著紙箱，終於累了。

---

（新的結尾）

審稿意見：
1. 角色動機需要更清晰。
"""

        self.assertEqual(clean_story_output(dirty), "橘貓夜遊\n\n小偵拆著紙箱，終於累了。")


if __name__ == "__main__":
    unittest.main()
