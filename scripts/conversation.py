from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re

from scripts.agent import get_agent_preset
from scripts.config import HarnessConfig
from scripts.outline import StoryInput


@dataclass(frozen=True)
class HarnessResult:
    run_dir: Path
    final_text: str


def load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text().strip()


def run_harness(
    story_input: StoryInput,
    config: HarnessConfig,
    writer_client,
    reviewer_client=None,
    progress=None,
) -> HarnessResult:
    # 這裡只處理單次 writer/reviewer 對話，不處理整本書、queue 或 CLI。
    reviewer_client = reviewer_client or writer_client
    runtime = config.runtime
    writer_preset = get_agent_preset(config, "writer")
    reviewer_preset = get_agent_preset(config, "reviewer")
    writer_model = writer_preset.get("model", "")
    reviewer_model = reviewer_preset.get("model", "")

    writer_prompt = load_prompt(runtime.writer_prompt_path)
    reviewer_prompt = load_prompt(runtime.reviewer_prompt_path)

    run_dir = create_run_dir(runtime.output_dir, story_input.title)
    (run_dir / "outline.md").write_text(story_input.outline.strip() + "\n")
    (run_dir / "target.md").write_text(story_target_markdown(story_input) + "\n")

    draft = ""
    review = ""
    for round_number in range(1, runtime.rounds + 1):
        progress_message(
            progress,
            f"round {round_number}/{runtime.rounds} writer start: {writer_model}",
        )
        draft = clean_story_output(
            writer_client.chat(
                writer_model,
                writer_messages(story_input, draft, review, writer_prompt),
                {
                    "num_ctx": runtime.num_ctx,
                    "num_predict": runtime.num_predict,
                    "temperature": runtime.writer_temperature,
                },
                runtime.keep_alive,
            )
        )
        write_round_file(run_dir, round_number, "draft", draft)
        progress_message(progress, f"round {round_number}/{runtime.rounds} writer done")
        if round_number == runtime.rounds:
            break

        progress_message(
            progress,
            f"round {round_number}/{runtime.rounds} reviewer start: {reviewer_model}",
        )
        review = reviewer_client.chat(
            reviewer_model,
            reviewer_messages(story_input, draft, reviewer_prompt),
            {
                "num_ctx": runtime.num_ctx,
                "num_predict": runtime.num_predict,
                "temperature": runtime.reviewer_temperature,
            },
            runtime.keep_alive,
        )
        write_round_file(run_dir, round_number, "review", review)
        progress_message(progress, f"round {round_number}/{runtime.rounds} reviewer done")

    draft = clean_story_output(draft)
    (run_dir / "final.md").write_text(draft.strip() + "\n")
    return HarnessResult(run_dir=run_dir, final_text=draft)


def clean_story_output(text: str) -> str:
    # 有些模型會把審稿意見或修改說明附在正文後面；這裡只做保守截斷。
    markers = [
        "\n---",
        "\n審稿意見：",
        "\n審稿意見:",
        "\n（新的結尾）",
        "\n(新的結尾)",
        "\n修改說明：",
        "\n修改說明:",
    ]
    cleaned = text.strip()
    cut_at = len(cleaned)
    for marker in markers:
        index = cleaned.find(marker)
        if index != -1:
            cut_at = min(cut_at, index)
    return cleaned[:cut_at].strip()


def progress_message(progress, message: str):
    if progress:
        progress(message)


def create_run_dir(output_dir: Path, title: str, today: date | None = None) -> Path:
    today = today or date.today()
    base_name = f"{today.strftime('%Y%m%d')}-{slugify_title(title)}"
    candidate = output_dir / base_name
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.strip(), flags=re.UNICODE).strip("-")
    return slug or "untitled"


def story_target_markdown(story_input: StoryInput) -> str:
    # target.md 是給人看的任務檔，也會被 writer/reviewer prompt 使用。
    parts = [
        "# 寫作目標",
        "",
        f"故事題目：{story_input.title}",
    ]
    if story_input.target_chapter is None:
        parts.extend(["", "目標：整篇故事"])
        return "\n".join(parts)

    parts.extend(
        [
            "",
            f"目標章節：{story_input.target_chapter_title}",
            "",
            "## 本章大綱",
            "",
            story_input.target_chapter_body.strip(),
        ]
    )
    return "\n".join(parts).strip()


def writer_messages(
    story_input: StoryInput,
    previous_draft: str,
    review: str,
    system_prompt: str,
):
    story_context = story_context_text(story_input)
    if not previous_draft:
        user_content = f"{story_context}\n\n請產出第一版。"
    else:
        user_content = (
            f"{story_context}\n\n"
            f"<上一版>\n{previous_draft.strip()}\n</上一版>\n\n"
            f"<審稿意見>\n{review.strip()}\n</審稿意見>\n\n"
            "請只輸出修訂後的完整故事，不要輸出審稿意見或修改說明。"
        )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def reviewer_messages(story_input: StoryInput, draft: str, system_prompt: str):
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"{story_context_text(story_input)}\n\n"
                f"<目前稿件>\n{draft.strip()}\n</目前稿件>\n\n"
                "請審稿。"
            ),
        },
    ]


def story_context_text(story_input: StoryInput) -> str:
    parts = [
        f"<完整大綱>\n{story_input.outline.strip()}\n</完整大綱>",
        f"<本次寫作目標>\n{story_target_markdown(story_input)}\n</本次寫作目標>",
    ]
    if story_input.previous_text.strip():
        parts.append(f"<已完成前文>\n{story_input.previous_text.strip()}\n</已完成前文>")
    return "\n\n".join(parts)


def write_round_file(run_dir: Path, round_number: int, kind: str, text: str):
    path = run_dir / f"round-{round_number:02d}-{kind}.md"
    path.write_text(text.strip() + "\n")
