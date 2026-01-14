# easytts 使用说明（WebUI）

easytts 是一个基于 **Genie-TTS / genie-tts（GPT-SoVITS ONNX 推理引擎）** 的 WebUI，用于在浏览器里进行文本转语音（TTS），并支持：

- 预设角色：自动从 Hugging Face 下载资源和角色模型，开箱即用
- 自定义模型：上传你自己的 **Genie-TTS ONNX 模型 zip**，再上传参考音频做情绪/语调克隆

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
- **自定义模型：需要参考音频 + 对应文本**。当前版本的推理流程依赖参考音频来提取说话人/风格信息，如果不提供，库会拒绝合成。

### A) 预设角色

1) 选择一个角色（如 `Mika / ThirtySeven / Feibi`）  
2) 选择“参考音频”模式：
   - **使用角色内置参考音频（情绪/风格）**：可选 `Normal/Sad/Fear/...`（不同角色可用项不同）
   - **上传参考音频（情绪/语调克隆）**：你上传一段音频 + 填写它对应的文本
3) 输入要合成的“文本”，点击“生成语音”  
4) 在“输出音频”里播放，或用“下载 WAV”保存

### B) 自定义模型

自定义模型需要你先把模型准备成 **zip** 并在 WebUI 里加载。

#### 1) 上传并加载 ONNX 模型

1) 填写“模型名称”（会作为 WebUI 里的角色名使用）  
2) 选择“模型语言”（`zh/en/jp/hybrid`）  
3) 上传你的 **ONNX 模型 zip**，点击“上传并加载模型”  
   - （可选）如果你希望**不再单独上传参考音频**，也可以把参考音频与 `prompt_wav.json` 一起打包进 zip（见下文“把参考音频一起打包”）
4) “加载状态”显示成功后，进入下一步

#### 2) 上传参考音频（必须）

1) 上传参考音频（建议 3~10 秒，干净人声，尽量无背景音乐）  
2) 填写“参考音频对应文本”（必须与音频里说的内容一致）  

支持的参考音频格式：`wav / flac / ogg / aiff / aif`

#### 2.1 把参考音频一起打包（可选，推荐）

你也可以把参考音频与文本直接放进模型 zip，让 WebUI 自动解析并在界面提供“内置参考（情绪/风格）”下拉框：

- 在 zip 中放一个 `prompt_wav.json`
- 并放一个 `prompt_wav/` 文件夹，里面是 `prompt_wav.json` 里 `wav` 字段对应的音频文件

示例结构：

- `your_model.zip`
  - `t2s_encoder_fp32.onnx` / `...`
  - `vits_fp32.onnx` / `...`
  - `prompt_wav.json`
  - `prompt_wav/`
    - `Normal.wav`
    - `Sad.ogg`

上传并加载成功后，在“参考音频”处选择“使用压缩包内置参考（情绪/风格）”即可，无需再单独上传参考音频。

#### 3) 合成

1) 输入要合成的“文本”  
2) 点击“生成语音”得到输出

## 3. ONNX 模型 zip 需要包含什么

zip 内应包含 Genie-TTS 需要的 ONNX 文件（通常在同一目录下）。常见必需文件包括：

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
