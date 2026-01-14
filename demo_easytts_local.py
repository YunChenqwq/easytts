from __future__ import annotations

from pathlib import Path

from easytts_client import EasyTTSLocal, EasyTTS


def main() -> None:
    tts = EasyTTSLocal()

    # 1) 预设角色 + 预设情绪（使用本地 CharacterModels 里的 prompt_wav.json + prompt_wav/）
    res = tts.tts_preset(
        text="私も昔、これと似たようなの持ってたなぁ…。",
        character="mika",
        preset="普通",
        out_path="local_preset.wav",
    )
    EasyTTS.save(res, "local_preset.wav")
    print("saved:", res.audio_url)

    # 2) 上传参考音频（本地路径）+ 参考文本（可选）
    ref = Path("ref.ogg")
    if ref.exists():
        res = tts.tts_upload(
            text="你好，今天心情有点难过。",
            character="mika",
            reference_audio=ref,
            reference_text="我今天心情真的很难过。",
            out_path="local_upload.wav",
        )
        EasyTTS.save(res, "local_upload.wav")
        print("saved:", res.audio_url)
    else:
        print("skip upload demo: ref.ogg not found")


if __name__ == "__main__":
    main()

