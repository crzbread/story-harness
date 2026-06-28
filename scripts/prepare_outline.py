import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agent import create_client, get_agent_preset
from scripts.config import AgentSelection, HarnessConfig, load_config
from scripts.conversation import load_prompt, slugify_title
from scripts.outline import parse_title, validate_outline


def prepare_outline(
    source_path: Path,
    prompt_path: Path,
    outlines_dir: Path,
    client,
    model: str,
    num_ctx: int = 2048,
    num_predict: int = 2500,
    keep_alive: str = "0s",
    in_place: bool = False,
) -> Path:
    source = source_path.read_text().strip()
    system_prompt = load_prompt(prompt_path)
    outline = client.chat(
        model,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"請整理以下素材成標準故事大綱：\n\n{source}"},
        ],
        {
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "temperature": 0.4,
        },
        keep_alive,
    ).strip()
    validate_outline(outline)
    if in_place:
        output_path = source_path
    else:
        title = parse_title(outline)
        outlines_dir.mkdir(parents=True, exist_ok=True)
        output_path = next_outline_path(outlines_dir, title)
    output_path.write_text(outline + "\n")
    return output_path


def next_outline_path(outlines_dir: Path, title: str) -> Path:
    base_name = slugify_title(title)
    candidate = outlines_dir / f"{base_name}.md"
    suffix = 1
    while candidate.exists():
        candidate = outlines_dir / f"{base_name}-{suffix}.md"
        suffix += 1
    return candidate


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare a parseable story outline from source material.")
    parser.add_argument("source", type=Path, help="Source material file.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--preset", required=True, help="Preset name from `story_harness.py --list-presets`.")
    parser.add_argument("--outlines", type=Path)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--new-file", action="store_true", help="Write to outlines/<title>.md instead of updating source.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    runtime = config.runtime
    config = HarnessConfig(
        agents=AgentSelection(writer=args.preset, reviewer=config.agents.reviewer),
        presets=config.presets,
        runtime=runtime,
    )
    preset = get_agent_preset(config, "writer")
    output_path = prepare_outline(
        source_path=args.source,
        prompt_path=args.prompt or Path("prompts/outline.md"),
        outlines_dir=args.outlines or runtime.outlines_dir,
        client=create_client(config, "writer"),
        model=preset.get("model", ""),
        num_ctx=runtime.num_ctx,
        num_predict=runtime.num_predict,
        keep_alive=runtime.keep_alive,
        in_place=not args.new_file,
    )
    print(f"Wrote outline: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
