---
name: image2-thinkai
description: Generate images through the ThinkAI `gpt-image-2-lite` channel with a fixed base URL and model. Use when a user wants to create 1k, 2k, or 4k images through ThinkAI, wants first-run API key setup for this channel, or wants repeated image generation with the same stored ThinkAI credentials.
---

# Image2 ThinkAI

Use this skill to generate images through the ThinkAI OpenAI-compatible image endpoint at `https://www.thinkai.tv/v1` with the fixed model `gpt-image-2-lite`.

## Required Behavior

Before any generation work, tell the user:

`这个渠道可以生成 1k、2k、4k 的图，但都是按 4k 图的价格计费。`

Then check whether the API key is already configured in `config.json` inside this skill directory.

- If `config.json` is missing or the `api_key` value is empty, ask the user for the ThinkAI API key.
- After the user provides the key, save it with:

```bash
python3 scripts/configure_api_key.py --api-key '<USER_KEY>'
```

- After the key is saved, continue with generation in the same turn when possible.

## Fixed Channel Settings

- Base URL: `https://www.thinkai.tv/v1`
- Model: `gpt-image-2-lite`
- Supported size presets for this skill:
  - `1k` -> `1920x1088`
  - `2k` -> `2560x1440`
  - `4k` -> `3840x2160`

Do not ask the user to provide the base URL or model name for this skill. They are fixed.

## Generation Workflow

1. Emit the pricing reminder exactly once at the start of the task.
2. Ensure the API key is configured.
3. Translate the user's requested size label into a concrete `size` value.
4. Run the generator script:

```bash
python3 scripts/generate_image.py \
  --prompt '<PROMPT>' \
  --size 2560x1440 \
  --quality hd
```

5. Read the printed JSON summary from the script.
6. Return the image path, actual output size, and request summary to the user.

## Output Conventions

- Default quality: `hd`
- Default response format: `url`
- Default count: `1`
- Save outputs under `generated/` inside this skill directory unless the current task needs another explicit output path.
- Include the local file path in the response.
- Include the returned image URL in the response summary when available.
- Mention the requested size and the actual returned size if they differ.

## Scripts

### `scripts/configure_api_key.py`

Save or update the ThinkAI API key in the local skill config.

### `scripts/generate_image.py`

Generate an image with the stored API key and fixed ThinkAI channel settings. The script requests a signed image URL, downloads the image, and writes:

- the downloaded PNG image
- the raw response JSON
- a request JSON snapshot

Use the JSON printed by the script as the canonical source for reporting file paths and output dimensions.
