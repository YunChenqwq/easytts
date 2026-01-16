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

## 使用说明

easytts 是一个基于 **Genie-TTS / genie-tts（GPT-SoVITS ONNX 推理引擎）** 的 WebUI，用于在浏览器里进行文本转语音（TTS），并支持：

- 预设角色：自动从 Hugging Face 下载资源和角色模型，开箱即用
- 自定义模型（推荐）：作为仓库所有者，把转换后的模型目录直接放进你的仓库（`models/<角色名>/...`），WebUI 启动后会自动识别并在“已导入模型”中可选

> 注意：本项目与上游依赖均有各自的开源协议要求；部署/二次分发请务必遵守（查看各项目 `LICENSE`）。

## 1. 最省事的方式：直接从 Hugging Face 复制

如果你看到的是 Hugging Face Spaces 页面：

1) 直接点击 **Duplicate Space / 复制 Space**  
2) （推荐）开启 **Persistent Storage**，这样下载的 `GenieData` 与模型会缓存到 `/data`，下次启动不用重下  
3) 打开 Space 的 WebUI 使用即可（首次下载可能需要几十秒到数分钟）

easytts 会自动下载：

- `GenieData`（约 391MB）
- 你选择的预设角色模型（首次使用该角色时下载）

## 2. WebUI 怎么用

打开 WebUI 后有两个页签：

## 2.1 参考音频是不是必须？

- **预设角色：不需要你手动上传参考音频**。因为每个预设角色自带了内置参考音频（情绪/风格），WebUI 默认直接使用它来合成（你也可以切换为“上传参考音频”来做更强的情绪/语调克隆）。
- **自定义模型：需要参考音频 + 对应文本**（可以“上传参考音频”，也可以使用你在模型目录里提供的 `prompt_wav/` 内置参考）。当前版本的推理流程依赖参考音频来提取说话人/风格信息，如果不提供，库会拒绝合成。

### A) 预设角色

1) 选择一个角色（如 `Mika / ThirtySeven / Feibi`）  
2) 选择“参考音频”模式：
   - **使用角色内置参考音频（情绪/风格）**：可选 `Normal/Sad/Fear/...`（不同角色可用项不同）
   - **上传参考音频（情绪/语调克隆）**：你上传一段音频 + 填写它对应的文本
3) 输入要合成的“文本”，点击“生成语音”  
4) 在“输出音频”里播放，或用“下载 WAV”保存

### B) 自定义模型

自定义模型推荐由“仓库所有者”离线转换后，直接提交到自己的魔搭（ModelScope）仓库中，让 WebUI 自动识别加载。

#### 1) 推荐方式：用转换工具生成模型目录，然后上传到你的魔搭仓库

1) 打开本仓库自带的转换工具：`tools/model_converter/easytts_model_converter_gui.py`  
2) 选择输入（通常是 GPT-SoVITS 的 `.pth` + `.ckpt`），填写模型名与语言，开始转换  
3) 输出根目录请选择你的 easytts 仓库里的 `models/`，工具会生成如下结构：  
   - `models/<角色名>/tts_models/`：ONNX/.bin（推理必需文件）  
   - `models/<角色名>/prompt_wav/`：参考音频（可选）  
   - `models/<角色名>/prompt_wav.json`：参考音频映射（可选）  
   - `models/<角色名>/(easytts_pack.json/_easytts_meta.json)`：元信息（建议保留）  
4) 把整个 `models/<角色名>/` 文件夹提交并推送到你自己的魔搭仓库  
5) 重启 / 刷新 WebUI，在“自定义模型”页签的“已导入模型”里选择该角色即可使用

#### 2) 上传参考音频（必须）

1) 上传参考音频（建议 3~10 秒，干净人声，尽量无背景音乐）  
2) 填写“参考音频对应文本”（必须与音频里说的内容一致）  

支持的参考音频格式：`wav / flac / ogg / aiff / aif`

#### 2.1 让模型自带“情绪/风格”下拉框（可选，推荐）

你可以把参考音频与文本放进 `models/<角色名>/prompt_wav/`，让 WebUI 自动解析并在界面提供“内置参考（情绪/风格）”下拉框：

- 方式 A：提供 `prompt_wav.json` + `prompt_wav/`（最稳定）
- 方式 B：只提供 `prompt_wav/`，并按约定放置：`<预设名>.<音频扩展名>` + `<预设名>.txt`（WebUI 会自动生成 `prompt_wav.json`）

示例结构（方式 B）：

- `models/<角色名>/`
  - `tts_models/`
  - `prompt_wav/`
    - `普通.wav`
    - `普通.txt`
    - `伤心.ogg`
    - `伤心.txt`

配置完成后，在“参考音频”处选择“使用内置参考（情绪/风格）”即可，无需再单独上传参考音频。

#### 3) 合成

1) 输入要合成的“文本”  
2) 点击“生成语音”得到输出

#### 4) 旧方式（兼容）：WebUI 上传 zip

仍然兼容“上传 zip 并解压导入”的方式，但不再推荐（对大型模型/频繁更新不友好，且更难管理版本）。

如果你仍要使用 zip，zip 内应包含 Genie-TTS 需要的 ONNX 文件（通常在同一目录下）。常见必需文件包括：

- `t2s_encoder_fp32.bin`
- `t2s_encoder_fp32.onnx`
- `t2s_first_stage_decoder_fp32.onnx`
- `t2s_shared_fp16.bin`
- `t2s_stage_decoder_fp32.onnx`
- `vits_fp16.bin`
- `vits_fp32.onnx`

> 提示：zip 外面多包一层目录也可以（WebUI 会尝试自动识别）。

## 4. 常见问题

### 访问 `http://0.0.0.0:7860` 显示 502

`0.0.0.0` 是“监听地址”，不是浏览器访问地址。请使用：

- `http://127.0.0.1:7860`
- `http://localhost:7860`

### 首次加载/生成很慢

首次需要下载 `GenieData` 和模型文件，属于正常现象。建议在 Spaces 开启 Persistent Storage 以便缓存。

## 5. 作为 Python 接口函数库调用（远程）

如果你已经把 easytts 部署到了 ModelScope / HuggingFace（能在浏览器里正常使用 WebUI），你也可以在自己的 Python 项目里直接调用“线上 WebUI”来合成语音。

### 5.1 配置 Token（两选一）

**方式 A：写本地配置文件（推荐本地开发）**

1) 复制 `easytts_secrets.example.py` 为 `easytts_secrets.py`
2) 填入 `EASYTTS_STUDIO_TOKEN`（注意：不要把 token 提交到 git，也不要发到聊天里）

**方式 B：环境变量（推荐部署/生产）**

- `EASYTTS_BASE_URL`：默认 `https://yunchenqwq-easytts.ms.show`
- `EASYTTS_STUDIO_TOKEN`：必填（机密）
- `EASYTTS_FN_INDEX`：默认 `3`
- `EASYTTS_TRIGGER_ID`：默认 `19`

### 5.2 代码示例

```python
from easytts_client import EasyTTS

tts = EasyTTS()

# 1) 使用预设角色 + 预设情绪（不需要你自己上传参考音频）
res = tts.tts_preset(text="私も昔、これと似たようなの持ってたなぁ…。", character="mika", preset="普通")
EasyTTS.save(res, "out_preset.wav")

# 2) 上传参考音频 + 参考文本（更强的情绪/语调克隆）
# 注意：reference_text 必须与参考音频里说的话一致
res = tts.tts_upload(
    text="你好，今天心情有点难过。",
    character="mika",
    preset="伤心",
    reference_audio="ref.ogg",   # 也可以传 bytes
    reference_text="我今天心情真的很难过。",
)
EasyTTS.save(res, "out_upload.wav")
```

## 6. 本地 Python 调用（不走云端）

如果你想在本地直接用 Python 调用（不通过 WebUI / 不通过云端），可以使用 `EasyTTSLocal`（内部直接调用 `genie_tts` 推理）。

前提：
- 已安装依赖（与你本地 WebUI 相同环境即可）
- 已有模型资源：`GenieData/` 与 `CharacterModels/`（第一次使用会自动下载/初始化，取决于你的网络与设置）

示例：

```python
from easytts_client import EasyTTSLocal, EasyTTS

tts = EasyTTSLocal()

# 预设角色 + 预设情绪（使用本地 prompt_wav.json + prompt_wav/）
res = tts.tts_preset(text="你好", character="mika", preset="普通", out_path="local_preset.wav")
EasyTTS.save(res, "local_preset.wav")

# 上传参考音频（本地文件）+ 参考文本
res = tts.tts_upload(
    text="你好，今天心情有点难过。",
    character="mika",
    reference_audio="ref.ogg",
    reference_text="我今天心情真的很难过。",
    out_path="local_upload.wav",
)
EasyTTS.save(res, "local_upload.wav")
```

## MaiBot 插件

- EasyttsPlugin（独立仓库）：`https://github.com/YunChenqwq/EasyttsPlugin`
