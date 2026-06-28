import json
import subprocess
import urllib.error
import urllib.request


class OllamaClient:
    # 這個 class 負責跟本機 Ollama 的 HTTP API 溝通。
    # 外面的程式只需要呼叫 chat()，不用知道 HTTP request 怎麼組。
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def chat(self, model, messages, options, keep_alive):
        # Ollama 的 /api/chat 需要 JSON payload；messages 是對話內容。
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": options,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` or the Ollama app running?"
            ) from exc

        try:
            return body["message"]["content"].strip()
        except KeyError as exc:
            raise RuntimeError(f"Unexpected Ollama response: {body}") from exc


class CommandClient:
    # 這個 class 把任何命令列工具包成 agent。
    # 只要那個工具能收 prompt、吐文字，就能放進 writer/reviewer 流程。
    def __init__(self, command: list[str], timeout: int = 1800):
        self.command = command
        self.timeout = timeout

    def chat(self, model, messages, options, keep_alive):
        # command provider 不懂 chat messages，所以先轉成純文字 prompt。
        prompt = messages_to_prompt(messages)

        command = build_command(self.command, prompt, model)
        uses_prompt_arg = any("{prompt}" in part for part in self.command)
        try:
            # subprocess.run 會執行外部命令；capture_output=True 代表收集 stdout/stderr。
            completed = subprocess.run(
                command,
                input=None if uses_prompt_arg else prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # 把 Python 內建 timeout 錯誤包成專案自己的 RuntimeError，外層比較好顯示。
            raise RuntimeError(
                f"命令列 agent 執行超時（{self.timeout}s）：{command[0]}"
            ) from exc
        except FileNotFoundError as exc:
            # 通常代表 command[0] 這個執行檔不存在，例如 agy/codex 沒安裝。
            raise RuntimeError(f"找不到命令列 agent 執行檔：{command[0]}") from exc
        if completed.returncode != 0:
            # returncode 不是 0 代表外部工具失敗；stderr 通常會有原因。
            raise RuntimeError(
                f"命令列 agent 執行失敗（exit {completed.returncode}）：{completed.stderr.strip()}"
            )
        return completed.stdout.strip()


def build_command(command_template: list[str], prompt: str, model: str | None) -> list[str]:
    # config 裡的 command 是 list，例如：
    # ["agy", "--model", "Gemini", "-p", "{prompt}"]
    # 這裡逐一替換 list 裡的 placeholder，避免自己手動組 shell 字串。
    return [
        part.replace("{prompt}", prompt).replace("{model}", model or "")
        for part in command_template
    ]


def messages_to_prompt(messages) -> str:
    # 把 OpenAI/Ollama 類型的 messages 轉成一般 CLI 工具可讀的純文字。
    parts = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts).strip()


def create_client(config, role: str):
    # 根據 writer/reviewer 選到的 preset 建立對應 client。
    provider = get_agent_preset(config, role)
    provider_name = provider.get("provider", provider.get("type"))
    provider_type = provider.get("type")
    if provider_name == "ollama" or provider_type == "ollama":
        return OllamaClient(config.runtime.ollama_url)

    if provider.get("type") != "command":
        raise ValueError(f"不支援的 agent provider 類型 `{provider_name}`：{provider.get('type')}")
    command = provider.get("command")
    if not isinstance(command, list) or not command:
        raise ValueError(f"Provider `{provider_name}` 必須設定非空的 command list。")
    return CommandClient(command, timeout=provider.get("timeout", 1800))


def get_agent_preset(config, role: str) -> dict:
    # role 只接受 writer/reviewer；寫錯時要直接失敗，避免默默用錯模型。
    if role == "writer":
        preset_name = config.agents.writer
    elif role == "reviewer":
        preset_name = config.agents.reviewer
    else:
        raise ValueError(f"未知的 agent 角色：{role}")
    preset = config.presets.get(preset_name)
    if not preset:
        raise ValueError(f"config 裡找不到 {role} 使用的 preset：{preset_name}")
    return preset
