# image2-thinkai

一个通过 ThinkAI OpenAI 兼容图片接口生成图片的 Codex skill。

## 通道信息

- Base URL: `https://www.thinkai.tv/v1`
- Model: `gpt-image-2-lite`
- 支持的尺寸预设：
- `1k` -> `1920x1080`
- `2k` -> `2560x1440`
- `4k` -> `3840x2160`

这个 skill 会发送 `User-Agent: curl/8.7.1`，用于避免 Cloudflare 拦截 Python 默认的 `urllib` 请求头。

## 配置

在本地配置 ThinkAI API key：

```bash
python3 scripts/configure_api_key.py --api-key '<YOUR_THINKAI_API_KEY>'
```

这会生成 `config.json`，该文件已被 git 忽略，不会上传到仓库。

## 生成图片

```bash
python3 scripts/generate_image.py \
  --prompt '美女' \
  --size 2560x1440 \
  --quality hd
```

生成的图片，以及请求/响应快照都会写入 `generated/` 目录，该目录已被 git 忽略。
