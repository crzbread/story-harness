from dataclasses import replace

from scripts.config import HarnessConfig
from scripts.conversation import HarnessResult, create_run_dir, run_harness
from scripts.outline import StoryInput, load_story_input, mark_outline_done, parse_chapters


def run_book_harness(
    story_input: StoryInput,
    config: HarnessConfig,
    writer_client,
    reviewer_client=None,
    progress=None,
) -> HarnessResult:
    # 這裡負責「一本書」的流程：拆章、逐章呼叫 conversation、最後合併 book.md。
    reviewer_client = reviewer_client or writer_client
    runtime = config.runtime
    chapters = parse_chapters(story_input.outline)
    if not chapters:
        return run_harness(
            story_input,
            config,
            writer_client,
            reviewer_client=reviewer_client,
            progress=progress,
        )

    run_dir = create_run_dir(runtime.output_dir, story_input.title)
    chapters_dir = run_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "outline.md").write_text(story_input.outline.strip() + "\n")

    final_chapters = []
    previous_text = ""
    for chapter_number, chapter_title, chapter_body in chapters:
        progress_message(progress, f"chapter {chapter_number} start: {chapter_title}")
        chapter_input = StoryInput(
            title=story_input.title,
            outline=story_input.outline,
            target_chapter=chapter_number,
            target_chapter_title=chapter_title,
            target_chapter_body=chapter_body,
            source_path=story_input.source_path,
            previous_text=previous_text,
        )

        # 每章放進自己的 chapter-XX-run 資料夾，方便回頭看每輪 draft/review。
        chapter_config = HarnessConfig(
            agents=config.agents,
            presets=config.presets,
            runtime=replace(
                runtime,
                output_dir=chapters_dir / f"chapter-{chapter_number:02d}-run",
            ),
        )
        chapter_result = run_harness(
            chapter_input,
            chapter_config,
            writer_client,
            reviewer_client=reviewer_client,
            progress=progress,
        )
        chapter_text = chapter_result.final_text.strip()
        chapter_path = chapters_dir / f"chapter-{chapter_number:02d}.md"
        chapter_path.write_text(chapter_text + "\n")
        final_chapters.append((chapter_title, chapter_text))
        previous_text = format_book(story_input.title, final_chapters)
        progress_message(progress, f"chapter {chapter_number} done: {chapter_title}")

    book = format_book(story_input.title, final_chapters)
    (run_dir / "book.md").write_text(book)
    return HarnessResult(run_dir=run_dir, final_text=book)


def run_outline_queue(
    config: HarnessConfig,
    writer_client,
    reviewer_client=None,
    progress=None,
) -> list[HarnessResult]:
    # queue 模式會一直讀 outlines_dir 裡第一個未完成 .md，跑完就寫 .done。
    reviewer_client = reviewer_client or writer_client
    results = []
    while True:
        try:
            story_input = load_story_input(config.runtime.outlines_dir, None, None)
        except FileNotFoundError:
            break
        story_input = StoryInput(
            title=story_input.title,
            outline=story_input.outline,
            target_chapter=None,
            target_chapter_title="全書",
            target_chapter_body="",
            source_path=story_input.source_path,
        )
        progress_message(progress, f"outline start: {story_input.source_path}")
        result = run_book_harness(
            story_input,
            config,
            writer_client,
            reviewer_client=reviewer_client,
            progress=progress,
        )
        mark_outline_done(story_input.source_path)
        progress_message(progress, f"outline done: {story_input.source_path}")
        progress_message(progress, f"book: {result.run_dir / 'book.md'}")
        results.append(result)
    return results


def format_book(title: str, chapters: list[tuple[str, str]]) -> str:
    # book.md 的結構很單純：一本書 H1，章節 H2，正文接在章節標題後。
    parts = [f"# {title.strip()}"]
    for chapter_title, chapter_text in chapters:
        parts.append(f"## {chapter_title.strip()}\n\n{chapter_text.strip()}")
    return "\n\n".join(parts).strip() + "\n"


def progress_message(progress, message: str):
    if progress:
        progress(message)
