import json
from dataclasses import dataclass, field
from pathlib import Path

from scripts.agent import get_agent_preset


@dataclass(frozen=True)
class AgentSelection:
    # 這裡只記錄 writer/reviewer 選擇的 preset 名稱；完整 preset 另外讀 presets.generated.json。
    writer: str = ""
    reviewer: str = ""


@dataclass(frozen=True)
class RuntimeConfig:
    # CLI、整本書 runner、單章 harness 共用的執行參數。
    rounds: int = 3
    output_dir: Path = Path("stories")
    outlines_dir: Path = Path("outlines")
    writer_prompt_path: Path = Path("prompts/writer.md")
    reviewer_prompt_path: Path = Path("prompts/reviewer.md")
    ollama_url: str = "http://localhost:11434"
    num_ctx: int = 2048
    num_predict: int = 800
    writer_temperature: float = 0.8
    reviewer_temperature: float = 0.3
    keep_alive: str = "0s"


@dataclass(frozen=True)
class HarnessConfig:
    agents: AgentSelection = field(default_factory=AgentSelection)
    presets: dict = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def load_config(path: Path) -> HarnessConfig:
    if not path.exists():
        return HarnessConfig()

    raw = json.loads(path.read_text())
    agents = raw.get("agents", {})
    presets = load_presets(path.with_name("presets.generated.json"))
    runtime = raw.get("runtime", {})
    return HarnessConfig(
        agents=AgentSelection(
            writer=agent_preset_name(agents, "writer", AgentSelection.writer),
            reviewer=agent_preset_name(agents, "reviewer", AgentSelection.reviewer),
        ),
        presets=presets,
        runtime=RuntimeConfig(
            rounds=runtime.get("rounds", RuntimeConfig.rounds),
            output_dir=Path(runtime.get("output_dir", RuntimeConfig.output_dir)),
            outlines_dir=Path(
                runtime.get("outlines_dir", runtime.get("data_dir", RuntimeConfig.outlines_dir))
            ),
            writer_prompt_path=Path(
                runtime.get("writer_prompt_path", RuntimeConfig.writer_prompt_path)
            ),
            reviewer_prompt_path=Path(
                runtime.get("reviewer_prompt_path", RuntimeConfig.reviewer_prompt_path)
            ),
            ollama_url=runtime.get("ollama_url", RuntimeConfig.ollama_url),
            num_ctx=runtime.get("num_ctx", RuntimeConfig.num_ctx),
            num_predict=runtime.get("num_predict", RuntimeConfig.num_predict),
            writer_temperature=runtime.get(
                "writer_temperature", RuntimeConfig.writer_temperature
            ),
            reviewer_temperature=runtime.get(
                "reviewer_temperature", RuntimeConfig.reviewer_temperature
            ),
            keep_alive=runtime.get("keep_alive", RuntimeConfig.keep_alive),
        ),
    )


def load_presets(path: Path) -> dict:
    # presets.generated.json 由 scripts/generate_presets.py 產生；不存在時回傳空 dict，讓後續 preset 檢查報錯。
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def agent_preset_name(agents: dict, role: str, default: str) -> str:
    # 新格式是 `"writer": "preset-name"`；舊格式 `{ "preset": "..." }` 暫時保留相容。
    value = agents.get(role, default)
    if isinstance(value, dict):
        return value.get("preset", default)
    return value


def print_presets(config: HarnessConfig):
    for name, preset in sorted(config.presets.items()):
        provider = preset.get("provider", preset.get("type", "unknown"))
        model = preset.get("model", "")
        effort = preset.get("effort", "")
        effort_text = f", effort={effort}" if effort else ""
        print(f"{name}: provider={provider}, model={model}{effort_text}")


def runtime_summary(config: HarnessConfig) -> str:
    runtime = config.runtime
    writer = get_agent_preset(config, "writer")
    reviewer = get_agent_preset(config, "reviewer")
    presets = [writer, reviewer]
    has_ollama = any(preset.get("type") == "ollama" for preset in presets)
    command_timeouts = [
        preset.get("timeout", 1800)
        for preset in presets
        if preset.get("type") == "command"
    ]
    parts = []
    if has_ollama:
        parts.append(
            f"Ollama runtime: keep_alive={runtime.keep_alive}, num_ctx={runtime.num_ctx}, num_predict={runtime.num_predict}"
        )
    if command_timeouts:
        timeout_text = ", ".join(f"timeout={timeout}s" for timeout in command_timeouts)
        parts.append(f"Command providers: {timeout_text}")
    return " | ".join(parts) if parts else "Runtime: default"
