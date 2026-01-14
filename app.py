import os
import tempfile
import json
import zipfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import gradio as gr


def _default_genie_data_dir() -> str:
    # Hugging Face Spaces persistent storage (if enabled) is usually mounted at /data
    if os.path.isdir("/data"):
        return os.path.join("/data", "GenieData")
    return os.path.join(os.getcwd(), "GenieData")


# Ensure non-interactive startup in Spaces (auto-download if missing)
os.environ.setdefault("GENIE_DATA_DIR", _default_genie_data_dir())
os.environ.setdefault("GENIE_AUTO_DOWNLOAD", "1")
os.environ.setdefault("Max_Cached_Character_Models", "2")
os.environ.setdefault("Max_Cached_Reference_Audio", "8")

import genie_tts as genie  # noqa: E402


PREDEFINED_CHARACTERS: Dict[str, Dict[str, str]] = {
    "mika": {"label": "Mika (日语)"},
    "thirtyseven": {"label": "ThirtySeven / 37 (英语)"},
    "feibi": {"label": "Feibi (中文)"},
}


def _make_wav_path(prefix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"genie_{prefix}_", suffix=".wav")
    os.close(fd)
    return path


def _model_root_dir() -> str:
    if os.path.isdir("/data"):
        return os.path.join("/data", "models")
    return os.path.join(os.getcwd(), "models")


def _safe_extract_zip(zip_path: str, dest_dir: str) -> None:
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or name.startswith("../") or "/../" in name:
                raise gr.Error("压缩包包含非法路径（疑似 ZipSlip）。请重新打包后再上传。")
            out_path = (dest / name).resolve()
            if dest not in out_path.parents and out_path != dest:
                raise gr.Error("压缩包包含非法路径（疑似 ZipSlip）。请重新打包后再上传。")
        zf.extractall(dest)


def _pick_onnx_model_dir(extracted_dir: str) -> str:
    required = {
        "t2s_encoder_fp32.bin",
        "t2s_encoder_fp32.onnx",
        "t2s_first_stage_decoder_fp32.onnx",
        "t2s_shared_fp16.bin",
        "t2s_stage_decoder_fp32.onnx",
        "vits_fp16.bin",
        "vits_fp32.onnx",
    }
    root = Path(extracted_dir)
    files = {p.name for p in root.iterdir() if p.is_file()}
    if required.issubset(files):
        return str(root)

    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        files2 = {p.name for p in subdirs[0].iterdir() if p.is_file()}
        if required.issubset(files2):
            return str(subdirs[0])

    return str(root)


def _find_first_file(root_dir: str, filename: str) -> Optional[str]:
    root = Path(root_dir)
    for p in root.rglob(filename):
        if p.is_file():
            return str(p)
    return None


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_demo() -> gr.Blocks:
    loaded: Set[str] = set()
    default_version = os.getenv("GENIE_CHARACTER_VERSION", "v2ProPlus")
    custom_loaded: Dict[str, str] = {}
    custom_prompts: Dict[str, Dict[str, Any]] = {}
    custom_prompt_dirs: Dict[str, str] = {}

    def ensure_character_loaded(character: str) -> None:
        if character in loaded:
            return
        genie.load_predefined_character(character)
        loaded.add(character)

    def _character_dir(character: str) -> str:
        return os.path.join(os.getcwd(), "CharacterModels", default_version, character)

    def _prompt_wav_json_path(character: str) -> str:
        return os.path.join(_character_dir(character), "prompt_wav.json")

    def _load_prompt_wav_json(character: str) -> Dict[str, Dict[str, str]]:
        path = _prompt_wav_json_path(character)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_preset_choices(character: str) -> Tuple[list[str], str]:
        data = _load_prompt_wav_json(character)
        if not data:
            return ["Normal"], "Normal"
        keys = list(data.keys())
        default = "普通" if "普通" in data else ("Normal" if "Normal" in data else keys[0])
        return keys, default

    def get_preset_text(character: str, preset: str) -> str:
        data = _load_prompt_wav_json(character)
        if not data:
            return ""
        item = data.get(preset) or next(iter(data.values()), None)
        if not item:
            return ""
        return item.get("text", "")

    def update_preset_ui(character: str):
        # If prompt_wav.json doesn't exist yet, try loading the character so the UI can show moods.
        if not os.path.exists(_prompt_wav_json_path(character)):
            ensure_character_loaded(character)
        choices, value = get_preset_choices(character)
        preset_text = get_preset_text(character, value)
        return (
            gr.Dropdown(choices=choices, value=value),
            gr.Textbox(value=preset_text),
        )

    def update_preset_text(character: str, preset: str):
        return gr.Textbox(value=get_preset_text(character, preset))

    def update_ref_mode_ui(mode: str):
        use_preset = mode == "preset"
        return (
            gr.Group(visible=use_preset),
            gr.Group(visible=not use_preset),
        )

    def synthesize(
        character: str,
        text: str,
        split_sentence: bool,
        ref_mode: str,
        preset_name: str,
        ref_audio_path: str,
        ref_audio_text: str,
    ) -> Tuple[str, str]:
        text = (text or "").strip()
        if not text:
            raise gr.Error("请输入要合成的文本。")

        ensure_character_loaded(character)

        if ref_mode == "preset":
            data = _load_prompt_wav_json(character)
            item = data.get(preset_name) if data else None
            if item and item.get("wav") and item.get("text"):
                audio_path = os.path.join(_character_dir(character), "prompt_wav", item["wav"])
                if os.path.exists(audio_path):
                    genie.set_reference_audio(
                        character_name=character,
                        audio_path=audio_path,
                        audio_text=item["text"],
                    )
        else:
            ref_audio_text = (ref_audio_text or "").strip()
            if not ref_audio_path or not os.path.exists(ref_audio_path):
                raise gr.Error("请上传参考音频（wav/flac/ogg/aiff/aif）。")
            if not ref_audio_text:
                raise gr.Error("请填写参考音频对应的文本（用于情绪/语调克隆）。")
            genie.set_reference_audio(
                character_name=character,
                audio_path=ref_audio_path,
                audio_text=ref_audio_text,
            )

        out_path = _make_wav_path(character)
        genie.tts(
            character_name=character,
            text=text,
            play=False,
            split_sentence=split_sentence,
            save_path=out_path,
        )
        return out_path, out_path

    def load_custom_model(model_name: str, language: str, model_zip_path: str) -> str:
        model_name = (model_name or "").strip()
        if not model_name:
            raise gr.Error("请填写模型名称（用于在本 WebUI 中区分角色）。")

        zip_path: str | None = None
        if isinstance(model_zip_path, list) and model_zip_path:
            item = model_zip_path[0]
            zip_path = getattr(item, "name", None) or (item if isinstance(item, str) else None)
        elif isinstance(model_zip_path, str):
            zip_path = model_zip_path
        else:
            zip_path = getattr(model_zip_path, "name", None)

        if not zip_path or not os.path.exists(zip_path):
            raise gr.Error("请上传 ONNX 模型压缩包（zip）。")

        root = _model_root_dir()
        dest = os.path.join(root, model_name)
        if os.path.exists(dest):
            shutil.rmtree(dest, ignore_errors=True)
        _safe_extract_zip(zip_path, dest)
        onnx_dir = _pick_onnx_model_dir(dest)

        genie.load_character(
            character_name=model_name,
            onnx_model_dir=onnx_dir,
            language=language,
        )
        custom_loaded[model_name] = onnx_dir

        prompt_json_path = _find_first_file(dest, "prompt_wav.json")
        if prompt_json_path:
            try:
                prompt_data = _read_json(prompt_json_path)
                prompt_dir = os.path.join(os.path.dirname(prompt_json_path), "prompt_wav")
                if os.path.isdir(prompt_dir) and isinstance(prompt_data, dict) and prompt_data:
                    custom_prompts[model_name] = prompt_data
                    custom_prompt_dirs[model_name] = prompt_dir
            except Exception:
                pass

        suffix = ""
        if model_name in custom_prompts:
            suffix = "\n检测到内置参考：prompt_wav.json（可在下方选择情绪/风格，无需再单独上传参考音频）"
        else:
            suffix = "\n未检测到内置参考：请在下方上传参考音频 + 文本"

        return f"已加载自定义模型：{model_name}\n模型目录：{onnx_dir}{suffix}"

    def synthesize_custom(
        model_name: str,
        text: str,
        split_sentence: bool,
        ref_mode: str,
        preset_name: str,
        ref_audio_path: str,
        ref_audio_text: str,
    ) -> Tuple[str, str]:
        model_name = (model_name or "").strip()
        if not model_name:
            raise gr.Error("请填写模型名称。")
        if model_name not in custom_loaded:
            raise gr.Error("该模型尚未加载。请先上传并加载 ONNX 模型。")

        text = (text or "").strip()
        if not text:
            raise gr.Error("请输入要合成的文本。")

        if ref_mode == "preset":
            data = custom_prompts.get(model_name) or {}
            prompt_dir = custom_prompt_dirs.get(model_name) or ""
            item = data.get(preset_name) if isinstance(data, dict) else None
            if not item:
                raise gr.Error("未找到内置参考信息，请切换到“上传参考音频”。")
            wav_name = item.get("wav")
            audio_text = (item.get("text") or "").strip()
            if not wav_name:
                raise gr.Error("内置参考缺少 wav 字段。")
            audio_path = os.path.join(prompt_dir, wav_name)
            if not os.path.exists(audio_path):
                raise gr.Error("内置参考音频文件不存在，请重新上传正确的 zip（包含 prompt_wav/ 与 prompt_wav.json）。")
            if not audio_text:
                raise gr.Error("内置参考缺少 text 字段。")
            genie.set_reference_audio(
                character_name=model_name,
                audio_path=audio_path,
                audio_text=audio_text,
            )
        else:
            ref_audio_text = (ref_audio_text or "").strip()
            if not ref_audio_path or not os.path.exists(ref_audio_path):
                raise gr.Error("请上传参考音频（wav/flac/ogg/aiff/aif）。")
            if not ref_audio_text:
                raise gr.Error("请填写参考音频对应的文本（用于情绪/语调克隆）。")
            genie.set_reference_audio(
                character_name=model_name,
                audio_path=ref_audio_path,
                audio_text=ref_audio_text,
            )

        out_path = _make_wav_path(model_name)
        genie.tts(
            character_name=model_name,
            text=text,
            play=False,
            split_sentence=split_sentence,
            save_path=out_path,
        )
        return out_path, out_path

    def custom_get_preset_choices(model_name: str) -> Tuple[list[str], str]:
        data = custom_prompts.get((model_name or "").strip()) or {}
        if not data:
            return ["Normal"], "Normal"
        keys = list(data.keys())
        default = "普通" if "普通" in data else ("Normal" if "Normal" in data else keys[0])
        return keys, default

    def custom_get_preset_text(model_name: str, preset: str) -> str:
        data = custom_prompts.get((model_name or "").strip()) or {}
        if not data:
            return ""
        item = data.get(preset) or next(iter(data.values()), None)
        if not item:
            return ""
        return (item.get("text") or "").strip()

    def custom_update_ref_mode_ui(mode: str):
        use_preset = mode == "preset"
        return (
            gr.Group(visible=use_preset),
            gr.Group(visible=not use_preset),
        )

    def custom_update_after_load(model_name: str):
        name = (model_name or "").strip()
        if name in custom_prompts:
            choices, value = custom_get_preset_choices(name)
            return (
                gr.Radio(value="preset"),
                gr.Dropdown(choices=choices, value=value),
                gr.Textbox(value=custom_get_preset_text(name, value)),
                gr.Group(visible=True),
                gr.Group(visible=False),
            )
        return (
            gr.Radio(value="upload"),
            gr.Dropdown(choices=["Normal"], value="Normal"),
            gr.Textbox(value=""),
            gr.Group(visible=False),
            gr.Group(visible=True),
        )

    def custom_update_preset_text(model_name: str, preset: str):
        return gr.Textbox(value=custom_get_preset_text(model_name, preset))

    with gr.Blocks(title="Genie-TTS WebUI") as demo:
        gr.Markdown(
            "## GENIE / Genie-TTS WebUI\n"
            "- 项目名称：`easytts`（仓库：`yunchenqwq/easytts`）\n"
            "- easytts 地址：https://github.com/yunchenqwq/easytts\n"
            "- Genie-TTS 原项目：https://github.com/High-Logic/Genie-TTS\n"
            "- 本项目基于 Genie-TTS / genie-tts 使用，部署与二次分发请务必遵守对应开源协议（见各项目 `LICENSE`）。\n"
            "- 首次使用某个角色时会自动从 Hugging Face 下载模型与资源（可能需要几十秒到数分钟）。\n"
            "- 本 WebUI 仅做推理演示，默认不播放音频，只生成并提供下载。"
        )

        with gr.Tabs():
            with gr.Tab("预设角色"):
                with gr.Row():
                    character = gr.Dropdown(
                        choices=[(v["label"], k) for k, v in PREDEFINED_CHARACTERS.items()],
                        value="mika",
                        label="角色 (Predefined Character)",
                    )
                    split_sentence = gr.Checkbox(value=True, label="自动分句 (split_sentence)")

                ref_mode = gr.Radio(
                    choices=[("使用角色内置参考音频（情绪/风格）", "preset"), ("上传参考音频（情绪/语调克隆）", "upload")],
                    value="preset",
                    label="参考音频",
                )

                preset_group = gr.Group(visible=True)
                with preset_group:
                    init_choices, init_value = get_preset_choices("mika")
                    preset_name = gr.Dropdown(choices=init_choices, value=init_value, label="内置参考（情绪/风格）")
                    preset_text = gr.Textbox(
                        value=get_preset_text("mika", init_value),
                        label="内置参考文本（只读）",
                        lines=2,
                        interactive=False,
                    )

                upload_group = gr.Group(visible=False)
                with upload_group:
                    ref_audio = gr.Audio(
                        label="上传参考音频（建议 3~10 秒，干净的人声）",
                        sources=["upload"],
                        type="filepath",
                        format="wav",
                    )
                    ref_text = gr.Textbox(
                        label="参考音频对应文本",
                        lines=2,
                        placeholder="填写你上传的参考音频里说的内容（与音频内容一致）。",
                    )

                text = gr.Textbox(
                    label="文本",
                    lines=4,
                    placeholder="输入要合成的文本（支持中文/英文/日文，取决于角色模型）。",
                )

                with gr.Row():
                    btn = gr.Button("生成语音", variant="primary")
                    audio = gr.Audio(label="输出音频", type="filepath", autoplay=False)
                    file = gr.File(label="下载 WAV")

                character.change(
                    fn=update_preset_ui,
                    inputs=[character],
                    outputs=[preset_name, preset_text],
                )
                preset_name.change(
                    fn=update_preset_text,
                    inputs=[character, preset_name],
                    outputs=[preset_text],
                )
                ref_mode.change(
                    fn=update_ref_mode_ui,
                    inputs=[ref_mode],
                    outputs=[preset_group, upload_group],
                )

                btn.click(
                    fn=synthesize,
                    inputs=[character, text, split_sentence, ref_mode, preset_name, ref_audio, ref_text],
                    outputs=[audio, file],
                    concurrency_limit=1,
                )

            with gr.Tab("自定义模型"):
                gr.Markdown(
                    "### 上传并加载 ONNX 模型\n"
                    "- 需要上传一个 `zip` 压缩包，里面是 Genie-TTS 需要的 ONNX 模型文件（若 zip 外面多包了一层目录也可以）。\n"
                    "- 可选：zip 里也可以同时放 `prompt_wav.json` + `prompt_wav/`（内置参考音频与文本），WebUI 会自动解析并在下方提供情绪/风格下拉选择。\n"
                    "- 加载成功后，再上传参考音频+文本即可合成。\n"
                    "- 提示：建议启用 Spaces 的 Persistent Storage，这样模型解压后可长期缓存到 `/data`。"
                )
                with gr.Row():
                    custom_name = gr.Textbox(value="custom", label="模型名称（也会作为角色名）")
                    custom_lang = gr.Dropdown(
                        choices=[
                            ("中文 (zh)", "zh"),
                            ("英文 (en)", "en"),
                            ("日语 (jp)", "jp"),
                            ("中英混合 (hybrid)", "hybrid"),
                        ],
                        value="zh",
                        label="模型语言",
                    )
                custom_zip = gr.File(label="ONNX 模型压缩包（zip）", file_types=[".zip"])
                load_btn = gr.Button("上传并加载模型", variant="primary")
                load_status = gr.Textbox(label="加载状态", lines=3, interactive=False)

                gr.Markdown("### 参考音频")
                custom_ref_mode = gr.Radio(
                    choices=[("使用压缩包内置参考（情绪/风格）", "preset"), ("上传参考音频（情绪/语调克隆）", "upload")],
                    value="upload",
                    label="参考音频",
                )

                custom_preset_group = gr.Group(visible=False)
                with custom_preset_group:
                    custom_preset = gr.Dropdown(choices=["Normal"], value="Normal", label="内置参考（情绪/风格）")
                    custom_preset_text = gr.Textbox(label="内置参考文本（只读）", lines=2, interactive=False)

                custom_upload_group = gr.Group(visible=True)
                with custom_upload_group:
                    custom_ref_audio = gr.Audio(
                        label="上传参考音频（建议 3~10 秒，干净的人声）",
                        sources=["upload"],
                        type="filepath",
                        format="wav",
                    )
                    custom_ref_text = gr.Textbox(
                        label="参考音频对应文本",
                        lines=2,
                        placeholder="填写你上传的参考音频里说的内容（与音频内容一致）。",
                    )

                custom_text = gr.Textbox(label="文本", lines=4)
                custom_split = gr.Checkbox(value=True, label="自动分句 (split_sentence)")

                with gr.Row():
                    custom_btn = gr.Button("生成语音", variant="primary")
                    custom_audio = gr.Audio(label="输出音频", type="filepath", autoplay=False)
                    custom_file = gr.File(label="下载 WAV")

                load_btn.click(
                    fn=load_custom_model,
                    inputs=[custom_name, custom_lang, custom_zip],
                    outputs=[load_status],
                    concurrency_limit=1,
                )
                load_btn.click(
                    fn=custom_update_after_load,
                    inputs=[custom_name],
                    outputs=[
                        custom_ref_mode,
                        custom_preset,
                        custom_preset_text,
                        custom_preset_group,
                        custom_upload_group,
                    ],
                    concurrency_limit=1,
                )
                custom_ref_mode.change(
                    fn=custom_update_ref_mode_ui,
                    inputs=[custom_ref_mode],
                    outputs=[custom_preset_group, custom_upload_group],
                )
                custom_preset.change(
                    fn=custom_update_preset_text,
                    inputs=[custom_name, custom_preset],
                    outputs=[custom_preset_text],
                )
                custom_btn.click(
                    fn=synthesize_custom,
                    inputs=[
                        custom_name,
                        custom_text,
                        custom_split,
                        custom_ref_mode,
                        custom_preset,
                        custom_ref_audio,
                        custom_ref_text,
                    ],
                    outputs=[custom_audio, custom_file],
                    concurrency_limit=1,
                )

    return demo


demo = build_demo()
demo.queue(default_concurrency_limit=1, max_size=16)

if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("GRADIO_SERVER_PORT") or "7860")
    demo.launch(server_name="0.0.0.0", server_port=port)
