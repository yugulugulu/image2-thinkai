#!/usr/bin/env python3

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional


SIZE_ALIASES = {
    "1k": "1920x1080",
    "2k": "2560x1440",
    "4k": "3840x2160",
}


def load_config(skill_dir: Path) -> dict:
    config_path = skill_dir / "config.json"
    if not config_path.exists():
        raise RuntimeError(
            f"Missing config at {config_path}. Ask the user for the ThinkAI API key and run "
            f"'python3 scripts/configure_api_key.py --api-key <KEY>'."
        )

    config = json.loads(config_path.read_text())
    api_key = str(config.get("api_key", "")).strip()
    if not api_key:
        raise RuntimeError(
            f"Empty api_key in {config_path}. Ask the user for the ThinkAI API key and run "
            f"'python3 scripts/configure_api_key.py --api-key <KEY>'."
        )
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an image through ThinkAI gpt-image-2-lite.")
    parser.add_argument("--prompt", required=True, help="Image prompt")
    parser.add_argument("--size", default="1920x1080", help="Size label or explicit size, e.g. 2k or 2560x1440")
    parser.add_argument("--quality", default="standard", choices=["standard", "hd"], help="Generation quality")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request")
    parser.add_argument("--output-dir", help="Directory for generated artifacts")
    return parser.parse_args()


def resolve_size(raw_size: str) -> str:
    normalized = raw_size.strip().lower()
    return SIZE_ALIASES.get(normalized, raw_size.strip())


def request_image(config: dict, prompt: str, size: str, quality: str, n: int) -> dict:
    base_url = str(config.get("base_url", "https://www.thinkai.tv/v1")).rstrip("/")
    model = str(config.get("model", "gpt-image-2-lite"))
    api_key = str(config["api_key"]).strip()

    body = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
    }

    req = urllib.request.Request(
        f"{base_url}/images/generations",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "curl/8.7.1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Image request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Image request failed: {exc}") from exc

    data = json.loads(payload)
    if "data" not in data or not data["data"] or "b64_json" not in data["data"][0]:
        raise RuntimeError(f"Unexpected response payload: {json.dumps(data, ensure_ascii=False)}")

    return {
        "request_body": body,
        "response_json": data,
    }


def get_png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Returned image is not a PNG file.")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    return width, height


def write_artifacts(skill_dir: Path, request_body: dict, response_json: dict, output_dir: Optional[str]) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else (skill_dir / "generated" / stamp)
    target_dir.mkdir(parents=True, exist_ok=True)

    image_bytes = base64.b64decode(response_json["data"][0]["b64_json"])
    width, height = get_png_dimensions(image_bytes)

    image_path = target_dir / "image.png"
    request_path = target_dir / "request.json"
    response_path = target_dir / "response.json"

    image_path.write_bytes(image_bytes)
    request_path.write_text(json.dumps(request_body, ensure_ascii=False, indent=2) + "\n")
    response_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2) + "\n")

    return {
        "image_path": str(image_path),
        "request_path": str(request_path),
        "response_path": str(response_path),
        "actual_size": f"{width}x{height}",
    }


def main():
    args = parse_args()
    skill_dir = Path(__file__).resolve().parent.parent

    try:
        config = load_config(skill_dir)
        size = resolve_size(args.size)
        result = request_image(config, args.prompt, size, args.quality, args.n)
        artifacts = write_artifacts(skill_dir, result["request_body"], result["response_json"], args.output_dir)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    summary = {
        "base_url": config.get("base_url"),
        "model": config.get("model"),
        "requested_size": size,
        "actual_size": artifacts["actual_size"],
        "quality": args.quality,
        "image_path": artifacts["image_path"],
        "request_path": artifacts["request_path"],
        "response_path": artifacts["response_path"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
