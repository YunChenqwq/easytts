---
title: easytts
emoji: 🎤
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
python_version: "3.10"
---

# easytts

easytts 是一个基于 **Genie-TTS / genie-tts（GPT-SoVITS ONNX 推理引擎）** 的 WebUI，用于在浏览器里进行文本转语音（TTS）。

## 项目与作者

- 本项目：`yunchenqwq/easytts`
  - 作者：yunchenqwq
  - GitHub 主页：`https://github.com/YunChenqwq`
  - 仓库地址：`https://github.com/YunChenqwq/easytts`
- 上游项目：Genie-TTS（项目来源）
  - `https://github.com/High-Logic/Genie-TTS`

## 重要提醒（开源协议）

本仓库与上游依赖均有各自的开源协议要求；部署/二次分发/商用前请务必阅读并遵守各项目的 `LICENSE`。

## 使用说明（中文）

- 详细操作文档：`USAGE_zh.md`

## 作为 Python 函数库调用（远程）

如果你已经把 easytts 部署到了 ModelScope / HuggingFace（能在浏览器里正常使用 WebUI），可以在 Python 里直接调用线上 WebUI：

- 入口：`easytts_client.py`（`EasyTTS`）
- 配置：复制 `easytts_secrets.example.py` 为 `easytts_secrets.py`，填入 token（不要提交到 git）
