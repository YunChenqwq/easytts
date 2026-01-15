# EasyttsPugin（MaiBot 插件）

本目录是一个 **MaiBot 插件**，用于把 `easytts` 的云端 Gradio（ModelScope Studio）语音合成能力接入到机器人里。

## 功能
- `/eztts` 命令把文本转语音
- 关键词触发的 Action（自动语音回复）
- 云端仓库池：可配置多个 `endpoints`，优先选择 `queue_size` 更小的仓库；当某个仓库繁忙/失败时自动切换
- 按情绪回复：Action/命令传入 `emotion` 时，后端会把情绪映射为预设（preset）（映射见 `config.toml` 的 `[easytts.emotion_preset_map]`）

## 安装
把整个 `EasyttsPugin/` 目录放进你的 MaiBot 插件目录（与其他插件同级）。

## 配置
编辑 `EasyttsPugin/config.toml`：
- 必填：`[[easytts.endpoints]]` 的 `base_url`（你的 ms.show 域名）和 `studio_token`
- 如你的 WebUI 不是默认按钮索引，修改 `fn_index` / `trigger_id`
- 如需按情绪：维护 `easytts.characters` 与 `[easytts.emotion_preset_map]`（情绪会映射为 preset）

推荐把多个仓库加入池中：
```toml
[[easytts.endpoints]]
name = "pool-1"
base_url = "https://xxx.ms.show"
studio_token = "..."

[[easytts.endpoints]]
name = "pool-2"
base_url = "https://yyy.ms.show"
studio_token = "..."
```

## 用法
- `/eztts 你好世界`
- `/eztts 今天天气不错 -v mika:普通`
- `/eztts 我有点难过 -v mika -e 伤心`

## 开源协议
本插件参考并改造自 `xuqian13/tts_voice_plugin`，因此本目录按 **AGPL-3.0** 进行分发。详见 `EasyttsPugin/NOTICE.md` 与 `EasyttsPugin/LICENSE`。

