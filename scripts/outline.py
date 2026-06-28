from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class StoryInput:
    # 一次 writer/reviewer 要處理的故事輸入。
    # target_chapter=None 代表整本書；有數字則代表只跑指定章節。
    title: str
    outline: str
    target_chapter: int | None
    target_chapter_title: str
    target_chapter_body: str
    source_path: Path
    previous_text: str = ""


def load_story_input(outlines_dir: Path, outline_path: Path | None, chapter: int | None) -> StoryInput:
    # outline_path 有值時讀指定檔案；沒有時從 outlines_dir 找第一個未完成大綱。
    source_path = outline_path or find_pending_outline(outlines_dir)
    outline = source_path.read_text().strip()
    validate_outline(outline, source_path)

    title = parse_title(outline)
    chapters = parse_chapters(outline)
    selected_chapter = chapter or 1
    for chapter_number, chapter_title, chapter_body in chapters:
        if chapter_number == selected_chapter:
            return StoryInput(
                title=title,
                outline=outline,
                target_chapter=chapter_number,
                target_chapter_title=chapter_title,
                target_chapter_body=chapter_body,
                source_path=source_path,
                previous_text="",
            )
    available = ", ".join(str(chapter_number) for chapter_number, _, _ in chapters)
    raise ValueError(f"{source_path} 找不到第 {selected_chapter} 章。可用章節：{available}")


def validate_outline(outline: str, source_path: Path | None = None):
    # 所有大綱格式檢查集中在這裡；其他函式只負責解析已通過檢查的文字。
    location = f"{source_path}：" if source_path else ""
    if not parse_title(outline):
        raise ValueError(f"大綱格式錯誤：{location}缺少 H1 故事標題，例如 `# 故事標題`。")
    if not chapter_headings(outline):
        raise ValueError(f"大綱格式錯誤：{location}缺少 H2 章節標題，例如 `## 第一章：開始`。")


def find_pending_outline(outlines_dir: Path) -> Path:
    # .done 檔存在代表該大綱已經跑過，queue 模式會跳過它。
    candidates = [
        path for path in sorted(outlines_dir.glob("*.md")) if not done_marker_for(path).exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"{outlines_dir} 底下沒有待執行的大綱 .md 檔。")
    return candidates[0]


def done_marker_for(outline_path: Path) -> Path:
    return outline_path.with_suffix(outline_path.suffix + ".done")


def mark_outline_done(outline_path: Path):
    done_marker_for(outline_path).write_text("done\n")


def parse_title(outline: str) -> str:
    # 標準格式只接受第一層 Markdown 標題當故事標題。
    for line in outline.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""


def parse_chapters(outline: str):
    # 只認 H2 標題；章節編號使用出現順序，不解析標題裡的「第幾章」。
    matches = chapter_headings(outline)
    chapters = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(outline)
        chapters.append(
            (
                index + 1,
                re.sub(r"^##\s*", "", match.group(0).strip()),
                outline[body_start:body_end].strip(),
            )
        )
    return chapters


def chapter_headings(outline: str):
    return list(re.finditer(r"(?m)^##\s+.+$", outline))
