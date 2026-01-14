from __future__ import annotations

from pathlib import Path

from easytts_client import EasyTTS


def main() -> None:
    """
    准备工作（二选一）：
    A) 复制 `easytts_secrets.example.py` -> `easytts_secrets.py`，并填好 EASYTTS_STUDIO_TOKEN
    B) 或设置环境变量 EASYTTS_STUDIO_TOKEN / EASYTTS_BASE_URL
    """

    # 默认禁用系统代理（避免 Windows “系统代理” 导致 requests 走 127.0.0.1:7890 报错）
    tts = EasyTTS(trust_env=False)

    # 1) 预设角色 + 预设情绪（不需要你自己上传参考音频）
    preset_result = tts.tts_preset(
        text="私も昔、これと似たようなの持ってたなぁ…。",
        character="mika",
        preset="普通",
    )
    EasyTTS.save(preset_result, "out_preset.wav")
    print("saved: out_preset.wav")
    print("audio_url:", preset_result.audio_url)

    # 2) 上传参考音频 + 参考文本（可选：把 ref.ogg 放到同目录）
    ref_path = Path("ref.ogg")
    if ref_path.exists():
        upload_result = tts.tts_upload(
            text="你好，今天心情有点难过。",
            character="mika",
            preset="伤心",
            reference_audio=ref_path,
            reference_text="我今天心情真的很难过。",
        )
        EasyTTS.save(upload_result, "out_upload.wav")
        print("saved: out_upload.wav")
        print("audio_url:", upload_result.audio_url)
    else:
        print("skip upload demo: ref.ogg not found")


if __name__ == "__main__":
    main()
