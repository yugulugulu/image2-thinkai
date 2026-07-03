#!/usr/bin/env python3

import argparse
import base64
import http.client
import json
import mimetypes
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional


SIZE_ALIASES = {
    "1k": "1920x1088",
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
    parser = argparse.ArgumentParser(description="Edit image(s) through ThinkAI gpt-image-2-4k.")
    parser.add_argument("--prompt", required=True, help="Edit instruction")
    parser.add_argument(
        "--image",
        action="append",
        required=True,
        help="Source image path. Repeat the flag to provide multiple images.",
    )
    parser.add_argument("--mask", help="Optional PNG mask path for inpainting")
    parser.add_argument("--size", default="auto", help="Size label or explicit size, e.g. 2k or 2560x1440")
    parser.add_argument("--quality", default="hd", help="Edit quality")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request")
    parser.add_argument("--output-dir", help="Directory for generated artifacts")
    return parser.parse_args()


def resolve_size(raw_size: str) -> str:
    normalized = raw_size.strip().lower()
    return SIZE_ALIASES.get(normalized, raw_size.strip())


def validate_inputs(image_paths: list[Path], mask_path: Optional[Path]) -> None:
    for image_path in image_paths:
        if not image_path.exists():
            raise RuntimeError(f"Source image not found: {image_path}")
        if not image_path.is_file():
            raise RuntimeError(f"Source image is not a file: {image_path}")

    if mask_path is None:
        return

    if not mask_path.exists():
        raise RuntimeError(f"Mask not found: {mask_path}")
    if not mask_path.is_file():
        raise RuntimeError(f"Mask is not a file: {mask_path}")
    if mask_path.suffix.lower() != ".png":
        raise RuntimeError("Mask must be a PNG file.")


def detect_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream"


def request_edit(config: dict, prompt: str, image_paths: list[Path], mask_path: Optional[Path], size: str, quality: str, n: int) -> dict:
    base_url = str(config.get("base_url", "https://www.thinkai.tv/v1")).rstrip("/")
    model = str(config.get("model", "gpt-image-2-4k"))
    api_key = str(config["api_key"]).strip()

    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        "--connect-timeout",
        "30",
        "--max-time",
        "900",
        "-X",
        "POST",
        f"{base_url}/images/edits",
        "-H",
        f"Authorization: Bearer {api_key}",
        "-H",
        "Accept: */*",
        "-H",
        "User-Agent: curl/8.7.1",
        "-F",
        f"model={model}",
        "-F",
        f"prompt={prompt}",
        "-F",
        f"size={size}",
        "-F",
        f"quality={quality}",
        "-F",
        f"n={n}",
    ]

    request_fields = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": n,
        "images": [str(path) for path in image_paths],
        "mask": str(mask_path) if mask_path else None,
    }

    for image_path in image_paths:
        cmd.extend(["-F", f"image=@{image_path};type={detect_content_type(image_path)}"])

    if mask_path is not None:
        cmd.extend(["-F", f"mask=@{mask_path};type=image/png"])

    result = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"curl exited with {result.returncode}"
        raise RuntimeError(f"Image edit request failed: {detail}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Image edit returned non-JSON payload: {result.stdout[:500]}") from exc

    if "data" not in data or not data["data"]:
        raise RuntimeError(f"Unexpected response payload: {json.dumps(data, ensure_ascii=False)}")

    first = data["data"][0]
    if "url" not in first and "b64_json" not in first:
        raise RuntimeError(f"Unexpected response payload: {json.dumps(data, ensure_ascii=False)}")

    return {
        "request_body": request_fields,
        "response_json": data,
    }


def get_png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Returned image is not a PNG file.")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    return width, height


def download_image(image_url: str) -> bytes:
    req = urllib.request.Request(
        image_url,
        headers={
            "Accept": "*/*",
            "User-Agent": "curl/8.7.1",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Image download failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        curl = subprocess.run(
            ["curl", "-L", "--fail", "--silent", "--show-error", image_url],
            capture_output=True,
            check=False,
            timeout=600,
        )
        if curl.returncode == 0 and curl.stdout:
            return curl.stdout
        stderr = curl.stderr.decode("utf-8", errors="replace").strip()
        if stderr:
            raise RuntimeError(f"Image download failed: {exc}; curl fallback failed: {stderr}") from exc
        raise RuntimeError(f"Image download failed: {exc}; curl fallback failed with exit code {curl.returncode}") from exc


def decode_image_bytes(response_json: dict) -> tuple[bytes, Optional[str]]:
    first = response_json["data"][0]
    if "b64_json" in first:
        return base64.b64decode(first["b64_json"]), None
    image_url = first["url"]
    return download_image(image_url), image_url


def write_artifacts(skill_dir: Path, request_body: dict, response_json: dict, output_dir: Optional[str]) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else (skill_dir / "generated" / f"edit-{stamp}")
    target_dir.mkdir(parents=True, exist_ok=True)

    image_bytes, image_url = decode_image_bytes(response_json)
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
        "image_url": image_url,
        "actual_size": f"{width}x{height}",
    }


def main():
    args = parse_args()
    skill_dir = Path(__file__).resolve().parent.parent
    image_paths = [Path(image).expanduser().resolve() for image in args.image]
    mask_path = Path(args.mask).expanduser().resolve() if args.mask else None

    try:
        validate_inputs(image_paths, mask_path)
        config = load_config(skill_dir)
        size = resolve_size(args.size)
        result = request_edit(config, args.prompt, image_paths, mask_path, size, args.quality, args.n)
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
        "source_images": [str(path) for path in image_paths],
        "mask_path": str(mask_path) if mask_path else None,
        "image_path": artifacts["image_path"],
        "image_url": artifacts["image_url"],
        "request_path": artifacts["request_path"],
        "response_path": artifacts["response_path"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
