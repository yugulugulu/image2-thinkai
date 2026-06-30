# image2-thinkai

Codex skill for generating images through the ThinkAI OpenAI-compatible image endpoint.

## Channel

- Base URL: `https://www.thinkai.tv/v1`
- Model: `gpt-image-2-lite`
- Supported size presets:
  - `1k` -> `1024x1024`
  - `2k` -> `2048x2048`
  - `4k` -> `4096x4096`

The skill sends `User-Agent: curl/8.7.1` to avoid Cloudflare blocking Python's default urllib user agent.

## Setup

Configure the ThinkAI API key locally:

```bash
python3 scripts/configure_api_key.py --api-key '<YOUR_THINKAI_API_KEY>'
```

This creates `config.json`, which is ignored by git.

## Generate

```bash
python3 scripts/generate_image.py \
  --prompt '美女' \
  --size 2048x2048 \
  --quality hd
```

Generated images and request/response snapshots are written under `generated/`, which is ignored by git.
