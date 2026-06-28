import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def build_presets(
    ollama_models=None,
    agy_models=None,
    codex_models=None,
    subscription_clis=None,
) -> dict:
    ollama_models = ollama_models or read_ollama_models
    agy_models = agy_models or read_agy_models
    codex_models = codex_models or read_codex_models
    subscription_clis = subscription_clis or read_subscription_clis

    presets = {}
    for model in sorted(ollama_models()):
        name = f"ollama-{slugify(model)}"
        presets[name] = {
            "type": "ollama",
            "provider": "ollama",
            "model": model,
        }
    for model in sorted(agy_models()):
        name = f"agy-{slugify(model)}"
        presets[name] = {
            "type": "command",
            "provider": "agy",
            "model": model,
            "command": [
                "agy",
                "--model",
                model,
                "--print-timeout",
                "30m",
                "-p",
                "{prompt}",
            ],
            "timeout": 1800,
        }
    for model, efforts in sorted(codex_models()):
        for effort in efforts:
            name = f"codex-{slugify(model)}-{slugify(effort)}"
            presets[name] = {
                "type": "command",
                "provider": "codex",
                "model": model,
                "effort": effort,
                "command": [
                    "codex",
                    "exec",
                    "--model",
                    model,
                    "-c",
                    f'model_reasoning_effort="{effort}"',
                    "-",
                ],
                "timeout": 1800,
            }
    for cli in sorted(subscription_clis()):
        if cli == "claude":
            presets["claude-default"] = {
                "type": "command",
                "provider": "claude",
                "model": "default",
                "command": ["claude", "--print", "{prompt}"],
                "timeout": 1800,
            }
    return presets


def read_ollama_models(
    base_url: str = "http://localhost:11434",
    urlopen=urllib.request.urlopen,
) -> list[str]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    return [
        model.get("name", "")
        for model in body.get("models", [])
        if isinstance(model, dict) and model.get("name")
    ]


def read_agy_models(command_runner=subprocess.run, cli_lookup=shutil.which) -> list[str]:
    if not cli_lookup("agy"):
        return []
    try:
        completed = command_runner(
            ["agy", "models"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return parse_agy_models(completed.stdout)


def parse_agy_models(output: str) -> list[str]:
    models = []
    for line in output.splitlines():
        model = line.strip()
        if not model:
            continue
        if model.lower().startswith("available models"):
            continue
        model = re.sub(r"^[-*•]\s*", "", model)
        model = re.sub(r"^\d+[.)]\s*", "", model)
        if model:
            models.append(model)
    return models


def read_codex_models(path: Path | None = None) -> list[tuple[str, list[str]]]:
    path = path or Path.home() / ".codex" / "models_cache.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return parse_codex_models_cache(raw)


def parse_codex_models_cache(raw: dict) -> list[tuple[str, list[str]]]:
    models = []
    for model in raw.get("models", []):
        if not isinstance(model, dict) or not model.get("slug"):
            continue
        efforts = [
            level.get("effort")
            for level in model.get("supported_reasoning_levels", [])
            if isinstance(level, dict) and level.get("effort")
        ]
        if efforts:
            models.append((model["slug"], efforts))
    return models


def read_subscription_clis(cli_lookup=shutil.which) -> list[str]:
    return [cli for cli in ("claude",) if cli_lookup(cli)]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "model"


def write_presets(
    path: Path,
    ollama_models=None,
    agy_models=None,
    codex_models=None,
    subscription_clis=None,
):
    presets = build_presets(
        ollama_models=ollama_models,
        agy_models=agy_models,
        codex_models=codex_models,
        subscription_clis=subscription_clis,
    )
    path.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n")
    return presets


def main():
    presets = write_presets(Path("presets.generated.json"))
    print(f"Wrote presets.generated.json with {len(presets)} detected presets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
