import os
import tempfile
import json
import zipfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import gradio as gr


_SUPPORTED_PROMPT_AUDIO_EXTS = (".wav", ".ogg", ".flac", ".mp3", ".aiff", ".aif")


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
    "sagiri": {"label": "Sagiri / 纱雾 (日语)"},
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


def _model_packs_dirs() -> list[str]:
    """
    Model pack zip directories (repo owners can upload zips here).

    - In Spaces/Studio, `/data` is persistent (if enabled).
    - We also scan repo workspace so owners can push zips via git/LFS.
    """
    dirs = [os.path.join(os.getcwd(), "ModelPacks")]
    if os.path.isdir("/data"):
        dirs.append(os.path.join("/data", "ModelPacks"))
    return dirs


def _safe_name(name: str) -> str:
    name = (name or "").strip()
    # Keep it conservative to avoid filesystem/URL issues.
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    out_name = "".join(out).strip("_")
    return out_name or "custom"


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_prompt_data_from_dir(prompt_dir: str) -> Dict[str, Dict[str, str]]:
    """
    Auto-build prompt_wav.json from a folder.

    Convention:
    - <preset>.<audio_ext>
    - <preset>.txt  (reference text that matches the audio content)
    """
    prompt_path = Path(prompt_dir)
    data: Dict[str, Dict[str, str]] = {}
    if not prompt_path.is_dir():
        return data

    for p in prompt_path.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in _SUPPORTED_PROMPT_AUDIO_EXTS:
            continue
        preset_name = p.stem.strip()
        if not preset_name:
            continue
        txt_path = p.with_suffix(".txt")
        if not txt_path.exists():
            continue
        try:
            txt = txt_path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not txt:
            continue
        data[preset_name] = {"wav": p.name, "text": txt}

    return data


def _try_load_or_build_prompts(model_dir: str) -> Tuple[Optional[Dict[str, Dict[str, str]]], Optional[str], str]:
    """
    Try to load prompts for a model dir:
    1) prompt_wav.json + prompt_wav/
    2) build from prompt_wav/ (audio + .txt)
    3) build from emotion/ (audio + .txt)

    Returns: (prompt_data, prompt_dir, message)
    """
    # 1) Existing prompt_wav.json
    prompt_json_path = _find_first_file(model_dir, "prompt_wav.json")
    if prompt_json_path:
        try:
            prompt_data = _read_json(prompt_json_path)
            prompt_dir = os.path.join(os.path.dirname(prompt_json_path), "prompt_wav")
            if os.path.isdir(prompt_dir) and isinstance(prompt_data, dict) and prompt_data:
                return prompt_data, prompt_dir, "检测到内置参考：prompt_wav.json"
        except Exception:
            pass

    # 2) Auto build from prompt_wav/
    prompt_dir = os.path.join(model_dir, "prompt_wav")
    built = _build_prompt_data_from_dir(prompt_dir)
    if built:
        # Persist for future runs
        _write_json(os.path.join(model_dir, "prompt_wav.json"), built)
        return built, prompt_dir, "已从 prompt_wav/ 自动生成 prompt_wav.json"

    # 3) Auto build from emotion/
    emotion_dir = os.path.join(model_dir, "emotion")
    built2 = _build_prompt_data_from_dir(emotion_dir)
    if built2:
        # Persist for future runs (note: wav filenames still reside in emotion/)
        _write_json(os.path.join(model_dir, "prompt_wav.json"), built2)
        return built2, emotion_dir, "已从 emotion/ 自动生成 prompt_wav.json"

    return None, None, "未检测到内置参考：请上传参考音频 + 文本"


def _meta_path(model_dir: str) -> str:
    return os.path.join(model_dir, "_easytts_meta.json")


def _load_meta(model_dir: str) -> Dict[str, Any]:
    p = _meta_path(model_dir)
    if not os.path.exists(p):
        return {}
    try:
        return _read_json(p)
    except Exception:
        return {}


def _save_meta(model_dir: str, *, model_name: str, language: str) -> None:
    _write_json(_meta_path(model_dir), {"model_name": model_name, "language": language})


def _read_pack_meta_from_zip(zip_path: str) -> Dict[str, Any]:
    """
    Optional metadata for ModelPacks/*.zip.

    Supported filenames inside zip (root or any subfolder):
    - easytts_pack.json
    - _easytts_meta.json
    - meta.json

    Expected keys:
    - model_name / name (str)
    - language (str): zh/en/jp/hybrid
    """
    candidates = {"easytts_pack.json", "_easytts_meta.json", "meta.json"}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                base = name.split("/")[-1]
                if base in candidates:
                    with zf.open(info) as f:
                        raw = f.read()
                    try:
                        return json.loads(raw.decode("utf-8"))
                    except Exception:
                        # Try utf-8-sig
                        return json.loads(raw.decode("utf-8-sig"))
    except Exception:
        pass
    return {}


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

    def has_required(dir_path: Path) -> bool:
        try:
            files = {p.name for p in dir_path.iterdir() if p.is_file()}
            return required.issubset(files)
        except Exception:
            return False

    # 0) Common Genie-TTS character layout: <model_root>/tts_models/
    tts_models_dir = root / "tts_models"
    if tts_models_dir.is_dir() and has_required(tts_models_dir):
        return str(tts_models_dir)

    # 1) Files directly in root
    if has_required(root):
        return str(root)

    # 2) One-level scan (handles multiple sibling dirs like prompt_wav/ + tts_models/)
    try:
        for sub in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name):
            if has_required(sub):
                return str(sub)
            # Prefer nested tts_models/ if present
            nested = sub / "tts_models"
            if nested.is_dir() and has_required(nested):
                return str(nested)
    except Exception:
        pass

    # 3) Two-level scan (handles CharacterModels/v2ProPlus/<name>/tts_models)
    try:
        for sub in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name):
            for sub2 in sorted([p for p in sub.iterdir() if p.is_dir()], key=lambda p: p.name):
                if has_required(sub2):
                    return str(sub2)
                nested = sub2 / "tts_models"
                if nested.is_dir() and has_required(nested):
                    return str(nested)
    except Exception:
        pass

    # 4) Recursive scan for common folder name `tts_models` (handles CharacterModels/v2ProPlus/<name>/tts_models)
    try:
        candidates: list[Path] = []
        for p in root.rglob("tts_models"):
            if p.is_dir() and has_required(p):
                candidates.append(p)
        if candidates:
            # Prefer the closest match
            candidates.sort(key=lambda p: (len(p.parts), str(p)))
            return str(candidates[0])
    except Exception:
        pass

    # 5) Last resort: find parent dir by locating one required file
    try:
        probe = root.rglob("t2s_encoder_fp32.bin")
        for f in probe:
            if f.is_file() and has_required(f.parent):
                return str(f.parent)
    except Exception:
        pass

    # Fallback: let genie_tts report missing files with a clear error.
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
    custom_languages: Dict[str, str] = {}

    def _auto_discover_models() -> str:
        """
        Auto load models that already exist on server:
        - ModelPacks/*.zip (repo owner uploads zips to this folder)
        - models/<name>/ (previously extracted models, including those uploaded via WebUI)
        """
        logs: list[str] = []
        root = _model_root_dir()
        os.makedirs(root, exist_ok=True)

        # Ensure ModelPacks folders exist
        for d in _model_packs_dirs():
            os.makedirs(d, exist_ok=True)

        # 1) Import zips from ModelPacks
        pack_zips: list[str] = []
        for d in _model_packs_dirs():
            try:
                for p in Path(d).glob("*.zip"):
                    if p.is_file():
                        pack_zips.append(str(p))
            except Exception:
                continue

        state_path = os.path.join(root, "_modelpacks_state.json")
        state: Dict[str, Any] = {}
        try:
            if os.path.exists(state_path):
                state = _read_json(state_path)
        except Exception:
            state = {}

        changed = False

        for zip_path in sorted(set(pack_zips)):
            try:
                meta_in_zip = _read_pack_meta_from_zip(zip_path)
                st = os.stat(zip_path)
                key = os.path.abspath(zip_path)
                sig = {"mtime": int(st.st_mtime), "size": int(st.st_size)}
                name_guess = _safe_name(str(meta_in_zip.get("model_name") or meta_in_zip.get("name") or Path(zip_path).stem))
                language = str(meta_in_zip.get("language") or "zh")
                dest = os.path.join(root, name_guess)

                prev = state.get(key) if isinstance(state, dict) else None
                need_extract = True
                if isinstance(prev, dict) and prev.get("sig") == sig and os.path.isdir(dest):
                    need_extract = False

                if need_extract:
                    if os.path.exists(dest):
                        shutil.rmtree(dest, ignore_errors=True)
                    _safe_extract_zip(zip_path, dest)
                    _save_meta(dest, model_name=name_guess, language=language)
                    state[key] = {"sig": sig, "model_name": name_guess, "language": language}
                    changed = True
                    logs.append(f"已导入模型包：{Path(zip_path).name} -> {name_guess}")
                else:
                    logs.append(f"模型包未变化，跳过解压：{Path(zip_path).name}")
            except Exception as e:
                logs.append(f"导入模型包失败：{zip_path} ({e})")

        if changed:
            try:
                _write_json(state_path, state)
            except Exception:
                pass

        # 2) Load all models from models/<name>/
        try:
            for p in Path(root).iterdir():
                if not p.is_dir():
                    continue
                if p.name.startswith("_"):
                    continue
                model_name = p.name
                if model_name in custom_loaded:
                    continue

                meta = _load_meta(str(p))
                language = str(meta.get("language") or "zh")

                # If no meta exists, still try to load with default language.
                onnx_dir = _pick_onnx_model_dir(str(p))
                try:
                    genie.load_character(
                        character_name=model_name,
                        onnx_model_dir=onnx_dir,
                        language=language,
                    )
                    custom_loaded[model_name] = onnx_dir
                    custom_languages[model_name] = language
                    _save_meta(str(p), model_name=model_name, language=language)
                except Exception as e:
                    logs.append(f"加载模型失败：{model_name} ({e})")
                    continue

                prompt_data, prompt_dir, prompt_msg = _try_load_or_build_prompts(str(p))
                if prompt_data and prompt_dir:
                    custom_prompts[model_name] = prompt_data
                    custom_prompt_dirs[model_name] = prompt_dir
                    logs.append(f"加载模型：{model_name}（{prompt_msg}）")
                else:
                    logs.append(f"加载模型：{model_name}（{prompt_msg}）")
        except Exception as e:
            logs.append(f"扫描 models/ 失败：{e}")

        if not logs:
            return "未发现任何可自动加载的模型（可把 zip 放到 ModelPacks/，或通过 WebUI 上传 zip 解压到 models/）。"
        return "\n".join(logs)

    auto_discover_log = _auto_discover_models()

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
        model_name = _safe_name(model_name)
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
        custom_languages[model_name] = language
        _save_meta(dest, model_name=model_name, language=language)

        prompt_data, prompt_dir, prompt_msg = _try_load_or_build_prompts(dest)
        if prompt_data and prompt_dir:
            custom_prompts[model_name] = prompt_data
            custom_prompt_dirs[model_name] = prompt_dir

        suffix = ""
        if model_name in custom_prompts:
            suffix = f"\n{prompt_msg}（可在下方选择情绪/风格，无需再单独上传参考音频）"
        else:
            suffix = f"\n{prompt_msg}"
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

    def select_existing_model(model_name: str):
        name = (model_name or "").strip()
        if not name:
            raise gr.Error("请选择一个已内置/已缓存的模型。")
        if name not in custom_loaded:
            raise gr.Error("该模型未加载（可能扫描失败）。请刷新页面或检查服务器日志。")

        lang = custom_languages.get(name, "zh")
        prompt_info = "未检测到内置参考"
        if name in custom_prompts:
            prompt_info = "已检测到内置参考（可选情绪/风格）"

        status = (
            f"已选择模型：{name}\n"
            f"模型目录：{custom_loaded.get(name)}\n"
            f"语言：{lang}\n"
            f"{prompt_info}"
        )

        ref_mode, preset_dd, preset_txt, preset_group, upload_group = custom_update_after_load(name)
        return (
            gr.Textbox(value=name),
            gr.Dropdown(value=lang),
            gr.Textbox(value=status),
            ref_mode,
            preset_dd,
            preset_txt,
            preset_group,
            upload_group,
        )

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
                    "- 仓库所有者可以把模型 zip 上传到 `ModelPacks/`（或 `/data/ModelPacks/`），WebUI 启动时会自动解压到 `models/` 并加载（可在下方直接选择使用）。\n"
                    "- 建议在 zip 里额外放一个 `easytts_pack.json`（或 `_easytts_meta.json` / `meta.json`），用于声明 `language`（zh/en/jp/hybrid）与可选的 `model_name`。\n"
                    "- 需要上传一个 `zip` 压缩包，里面是 Genie-TTS 需要的 ONNX 模型文件（若 zip 外面多包了一层目录也可以）。\n"
                    "- 可选：zip 里也可以同时放 `prompt_wav.json` + `prompt_wav/`（内置参考音频与文本），WebUI 会自动解析并在下方提供情绪/风格下拉选择。\n"
                    "- 新增：如果 zip 里只有 `prompt_wav/`（或 `emotion/`）且每个音频旁边有同名 `.txt` 参考文本，WebUI 会自动生成 `prompt_wav.json`，并把音频当作内置参考。\n"
                    "- 加载成功后，再上传参考音频+文本即可合成。\n"
                    "- 提示：建议启用 Spaces 的 Persistent Storage，这样模型解压后可长期缓存到 `/data`。"
                )

                gr.Markdown("### 已内置/已缓存的模型（无需再次上传 zip）")
                auto_log = gr.Textbox(value=auto_discover_log, label="自动扫描日志（只读）", lines=6, interactive=False)
                existing_models = gr.Dropdown(
                    choices=sorted(custom_loaded.keys()),
                    value=None,
                    label="选择一个模型",
                )
                use_existing_btn = gr.Button("使用该模型", variant="secondary")

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

                use_existing_btn.click(
                    fn=select_existing_model,
                    inputs=[existing_models],
                    outputs=[
                        custom_name,
                        custom_lang,
                        load_status,
                        custom_ref_mode,
                        custom_preset,
                        custom_preset_text,
                        custom_preset_group,
                        custom_upload_group,
                    ],
                    concurrency_limit=1,
                )

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
