import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_presets import (
    build_presets,
    parse_agy_models,
    parse_codex_models_cache,
    read_ollama_models,
    slugify,
    write_presets,
)


class GeneratePresetsTest(unittest.TestCase):
    def test_build_presets_uses_detected_models_only(self):
        presets = build_presets(
            ollama_models=lambda: ["qwen3:8b"],
            agy_models=lambda: ["Gemini 3.5 Flash (Low)"],
            codex_models=lambda: [("gpt-5.5", ["low", "medium"])],
            subscription_clis=lambda: ["claude"],
        )

        self.assertEqual(presets["ollama-qwen3-8b"]["model"], "qwen3:8b")
        self.assertEqual(
            presets["agy-gemini-3-5-flash-low"]["model"],
            "Gemini 3.5 Flash (Low)",
        )
        self.assertEqual(presets["codex-gpt-5-5-medium"]["effort"], "medium")
        self.assertEqual(presets["claude-default"]["provider"], "claude")
        self.assertNotIn("gemini-default", presets)
        self.assertNotIn("ollama-qwen3-14b", presets)
        self.assertNotIn("agy-claude-sonnet-4-6-thinking", presets)
        self.assertNotIn("codex-gpt-5-5-high", presets)

    def test_write_presets_writes_pretty_json_with_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "presets.generated.json"

            write_presets(
                path,
                ollama_models=lambda: ["llama3:latest"],
                agy_models=lambda: [],
                codex_models=lambda: [],
                subscription_clis=lambda: [],
            )

            text = path.read_text()
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(
                json.loads(text),
                build_presets(
                    ollama_models=lambda: ["llama3:latest"],
                    agy_models=lambda: [],
                    codex_models=lambda: [],
                    subscription_clis=lambda: [],
                ),
            )

    def test_read_ollama_models_returns_empty_when_ollama_is_unavailable(self):
        def failing_urlopen(request, timeout):
            raise OSError("offline")

        self.assertEqual(read_ollama_models(urlopen=failing_urlopen), [])

    def test_parse_agy_models_uses_output_lines_as_model_names(self):
        output = """
Available models:
- Gemini 3.5 Flash (Low)
* Claude Sonnet 4.6 (Thinking)
"""

        self.assertEqual(
            parse_agy_models(output),
            ["Gemini 3.5 Flash (Low)", "Claude Sonnet 4.6 (Thinking)"],
        )

    def test_parse_codex_models_cache_reads_slug_and_efforts(self):
        raw = {
            "models": [
                {
                    "slug": "gpt-5.5",
                    "supported_reasoning_levels": [
                        {"effort": "low"},
                        {"effort": "high"},
                    ],
                }
            ]
        }

        self.assertEqual(parse_codex_models_cache(raw), [("gpt-5.5", ["low", "high"])])

    def test_slugify_normalizes_provider_names(self):
        self.assertEqual(slugify("Gemini 3.5 Flash (Low)"), "gemini-3-5-flash-low")


if __name__ == "__main__":
    unittest.main()
