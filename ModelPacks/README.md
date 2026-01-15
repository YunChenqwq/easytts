# ModelPacks（模型包投放目录）

把自定义 ONNX 模型 **zip** 放到这个目录后，`app.py` 启动时会自动：
- 解压到 `models/<model_name>/`
- 调用 `genie.load_character(...)` 加载
- 若 zip 内包含 `prompt_wav/` 或 `emotion/` 且每个音频旁边有同名 `.txt`，会自动生成 `prompt_wav.json` 作为“内置参考（情绪/风格）”

建议在 zip 内放一个 `easytts_pack.json`（或 `_easytts_meta.json` / `meta.json`），例如：
```json
{
  "model_name": "mika",
  "language": "jp"
}
```

注意：大模型文件建议使用 LFS（按平台要求）上传。

