#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


SIZE_ALIASES = {
    "1k": "1920x1088",
    "2k": "2560x1440",
    "4k": "3840x2160",
}

CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 900
MAX_REQUEST_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 524}


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
    parser = argparse.ArgumentParser(description="Generate an image through ThinkAI gpt-image-2-4k.")
    parser.add_argument("--prompt", required=True, help="Image prompt")
    parser.add_argument("--size", default="1920x1080", help="Size label or explicit size, e.g. 2k or 2560x1440")
    parser.add_argument("--quality", default="hd", choices=["standard", "hd"], help="Generation quality")
    parser.add_argument("--n", type=int, default=1, help="Number of images to request")
    parser.add_argument("--output-dir", help="Directory for generated artifacts")
    return parser.parse_args()


def resolve_size(raw_size: str) -> str:
    normalized = raw_size.strip().lower()
    return SIZE_ALIASES.get(normalized, raw_size.strip())


def build_request_context(config: dict) -> tuple[str, str, dict]:
    base_url = str(config.get("base_url", "https://www.thinkai.tv/v1")).rstrip("/")
    model = str(config.get("model", "gpt-image-2-4k"))
    api_key = str(config["api_key"]).strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "curl/8.7.1",
    }
    return base_url, model, headers


def request_json(method: str, url: str, headers: dict, body: Optional[dict] = None) -> dict:
    last_error: Optional[Exception] = None
    payload = None

    for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
        try:
            resp = requests.request(
                method,
                url,
                json=body,
                headers=headers,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            resp.raise_for_status()
            payload = resp.text
            break
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            detail = exc.response.text if exc.response is not None else str(exc)
            if status_code in RETRYABLE_HTTP_STATUS_CODES and attempt < MAX_REQUEST_ATTEMPTS:
                last_error = RuntimeError(f"Image request failed with HTTP {status_code}: {detail}")
                time.sleep(attempt)
                continue
            raise RuntimeError(f"Image request failed with HTTP {status_code}: {detail}") from exc
        except (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ) as exc:
            if attempt < MAX_REQUEST_ATTEMPTS:
                last_error = exc
                time.sleep(attempt)
                continue
            raise RuntimeError(f"Image request failed: {exc}") from exc
    else:
        raise RuntimeError(f"Image request failed: {last_error}")

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Image request returned non-JSON payload: {payload[:500]}") from exc


def build_generation_body(model: str, prompt: str, size: str, quality: str, n: int) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "quality": quality,
        "response_format": "url",
    }


def request_sync_image(config: dict, prompt: str, size: str, quality: str, n: int) -> dict:
    base_url, model, headers = build_request_context(config)
    body = build_generation_body(model, prompt, size, quality, n)
    data = request_json("POST", f"{base_url}/images/generations", headers, body)

    if "data" not in data or not data["data"] or "url" not in data["data"][0]:
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


def write_artifacts(
    skill_dir: Path,
    request_body: dict,
    response_json: dict,
    output_dir: Optional[str],
) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else (skill_dir / "generated" / stamp)
    target_dir.mkdir(parents=True, exist_ok=True)

    image_url = response_json["data"][0]["url"]
    image_bytes = download_image(image_url)
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

    try:
        config = load_config(skill_dir)
        size = resolve_size(args.size)
        result = request_sync_image(config, args.prompt, size, args.quality, args.n)
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
        "image_url": artifacts["image_url"],
        "request_path": artifacts["request_path"],
        "response_path": artifacts["response_path"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
