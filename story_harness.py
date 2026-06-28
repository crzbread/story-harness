#!/usr/bin/env python3
import argparse
import sys
from dataclasses import replace
from pathlib import Path

from scripts.agent import CommandClient, OllamaClient, create_client, get_agent_preset
from scripts.config import (
    AgentSelection,
    HarnessConfig,
    RuntimeConfig,
    load_config,
    print_presets,
    runtime_summary,
)
from scripts.conversation import HarnessResult, clean_story_output, load_prompt, run_harness
from scripts.outline import (
    StoryInput,
    done_marker_for,
    load_story_input,
    mark_outline_done,
)
from scripts.runner import format_book, run_book_harness, run_outline_queue


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Story writer/reviewer harness.")
    parser.add_argument("prompt", nargs="?", help="Optional one-off instruction appended to the outline target.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--list-presets", action="store_true")
    parser.add_argument("--outlines", type=Path)
    parser.add_argument("--outline", type=Path)
    parser.add_argument("--chapter", type=int, help="Debug mode: only run one chapter.")
    parser.add_argument("--writer", help="Writer preset name.")
    parser.add_argument("--reviewer", help="Reviewer preset name.")
    parser.add_argument("--rounds", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--num-ctx", type=int)
    parser.add_argument("--num-predict", type=int)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    config = load_config(args.config)
    if args.list_presets:
        print_presets(config)
        return 0
    runtime = config.runtime
    config = HarnessConfig(
        agents=AgentSelection(
            writer=args.writer or config.agents.writer,
            reviewer=args.reviewer or config.agents.reviewer,
        ),
        presets=config.presets,
        runtime=replace(
            runtime,
            rounds=args.rounds if args.rounds is not None else runtime.rounds,
            output_dir=args.out or runtime.output_dir,
            outlines_dir=args.outlines or runtime.outlines_dir,
            ollama_url=args.url or runtime.ollama_url,
            num_ctx=args.num_ctx if args.num_ctx is not None else runtime.num_ctx,
            num_predict=(
                args.num_predict if args.num_predict is not None else runtime.num_predict
            ),
        ),
    )

    runtime = config.runtime
    if runtime.rounds < 1 or runtime.rounds > 10:
        print("--rounds must be between 1 and 10.", file=sys.stderr)
        return 2
    try:
        get_agent_preset(config, "writer")
        get_agent_preset(config, "reviewer")
        load_prompt(runtime.writer_prompt_path)
        load_prompt(runtime.reviewer_prompt_path)
        story_input = (
            load_story_input(runtime.outlines_dir, args.outline, args.chapter)
            if args.outline or args.chapter
            else None
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if story_input and args.chapter is None and story_input.target_chapter is not None:
        story_input = StoryInput(
            title=story_input.title,
            outline=story_input.outline,
            target_chapter=None,
            target_chapter_title="全書",
            target_chapter_body="",
            source_path=story_input.source_path,
        )
    if story_input and args.prompt:
        story_input = StoryInput(
            title=story_input.title,
            outline=story_input.outline,
            target_chapter=story_input.target_chapter,
            target_chapter_title=story_input.target_chapter_title,
            target_chapter_body=f"{story_input.target_chapter_body.strip()}\n\n補充指令：{args.prompt.strip()}",
            source_path=story_input.source_path,
        )
    def print_progress(message):
        print(message, flush=True)

    writer_preset = get_agent_preset(config, "writer")
    reviewer_preset = get_agent_preset(config, "reviewer")
    print(f"Run directory: {runtime.output_dir}", flush=True)
    if story_input:
        print(f"Outline: {story_input.source_path}", flush=True)
        print(f"Target: {story_input.target_chapter_title}", flush=True)
    else:
        print(f"Outline queue: {runtime.outlines_dir}", flush=True)
    print(
        (
            f"Using writer={config.agents.writer}:{writer_preset.get('model', '')}, "
            f"reviewer={config.agents.reviewer}:{reviewer_preset.get('model', '')}, "
            f"rounds={runtime.rounds}"
        ),
        flush=True,
    )
    print(
        runtime_summary(config),
        flush=True,
    )
    writer_client = create_client(config, "writer")
    reviewer_client = create_client(config, "reviewer")
    if story_input is None:
        results = run_outline_queue(
            config,
            writer_client,
            reviewer_client=reviewer_client,
            progress=print_progress,
        )
        print(f"Completed outlines: {len(results)}")
        if not results:
            print(f"No pending outlines found under {runtime.outlines_dir}")
        return 0

    if args.chapter is None:
        result = run_book_harness(
            story_input,
            config,
            writer_client,
            reviewer_client=reviewer_client,
            progress=print_progress,
        )
        mark_outline_done(story_input.source_path)
        print(f"Wrote run to {result.run_dir}")
        print(f"Final book: {result.run_dir / 'book.md'}")
        print(f"Marked outline done: {done_marker_for(story_input.source_path)}")
        return 0

    result = run_harness(
        story_input,
        config,
        writer_client,
        reviewer_client=reviewer_client,
        progress=print_progress,
    )
    print(f"Wrote run to {result.run_dir}")
    print(f"Final story: {result.run_dir / 'final.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
