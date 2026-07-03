#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Configure ThinkAI API key for the image2-thinkai skill.")
    parser.add_argument("--api-key", required=True, help="ThinkAI API key")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    config_path = skill_dir / "config.json"

    config = {
        "base_url": "https://www.thinkai.tv/v1",
        "model": "gpt-image-2-4k",
        "api_key": args.api_key.strip(),
    }

    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved config to {config_path}")


if __name__ == "__main__":
    main()
