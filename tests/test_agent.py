import sys
import unittest
from types import SimpleNamespace

from scripts.agent import CommandClient, create_client, get_agent_preset, messages_to_prompt


class AgentTest(unittest.TestCase):
    def test_messages_to_prompt_keeps_roles_and_content(self):
        messages = [
            {"role": "system", "content": "你是作者。"},
            {"role": "user", "content": "請寫第一版。"},
        ]

        prompt = messages_to_prompt(messages)

        self.assertEqual(prompt, "[system]\n你是作者。\n\n[user]\n請寫第一版。")

    def test_command_client_sends_prompt_to_stdin_when_command_has_no_prompt_placeholder(self):
        client = CommandClient([sys.executable, "-c", "import sys; print(sys.stdin.read())"])

        output = client.chat("", [{"role": "user", "content": "hello"}], {}, "")

        self.assertEqual(output, "[user]\nhello")

    def test_command_client_timeout_raises_runtime_error(self):
        client = CommandClient(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            timeout=0.01,
        )

        with self.assertRaises(RuntimeError) as error:
            client.chat("", [{"role": "user", "content": "hello"}], {}, "")

        self.assertIn("命令列 agent 執行超時", str(error.exception))

    def test_command_client_missing_executable_raises_chinese_error(self):
        client = CommandClient(["definitely-missing-story-harness-command"])

        with self.assertRaises(RuntimeError) as error:
            client.chat("", [{"role": "user", "content": "hello"}], {}, "")

        self.assertIn("找不到命令列 agent 執行檔", str(error.exception))

    def test_create_client_rejects_invalid_role(self):
        config = SimpleNamespace(
            agents=SimpleNamespace(writer="writer-preset", reviewer="reviewer-preset"),
            presets={
                "writer-preset": {"type": "command", "command": [sys.executable, "-c", ""]},
                "reviewer-preset": {"type": "command", "command": [sys.executable, "-c", ""]},
            },
            runtime=SimpleNamespace(ollama_url="http://localhost:11434"),
        )

        with self.assertRaises(ValueError) as error:
            get_agent_preset(config, "editor")

        self.assertIn("未知的 agent 角色", str(error.exception))

    def test_create_client_requires_non_empty_command_list(self):
        config = SimpleNamespace(
            agents=SimpleNamespace(writer="bad-command", reviewer="bad-command"),
            presets={"bad-command": {"type": "command", "command": []}},
            runtime=SimpleNamespace(ollama_url="http://localhost:11434"),
        )

        with self.assertRaises(ValueError) as error:
            create_client(config, "writer")

        self.assertIn("必須設定非空的 command list", str(error.exception))


if __name__ == "__main__":
    unittest.main()
