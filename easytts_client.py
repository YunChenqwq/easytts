from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Union

from easytts_remote_client import EasyTTSRemoteClient, RemoteAudioResult
from easytts_tokens import EasyTTSRemoteConfig, load_remote_config


@dataclass(frozen=True)
class TTSResult:
    audio_bytes: bytes
    audio_url: str
    orig_name: Optional[str] = None


class EasyTTS:
    """
    Python interface library for calling a deployed easytts Gradio app remotely.

    Token config:
    - Create `easytts_secrets.py` (gitignored) OR set environment variables.
    - See `easytts_secrets.example.py`.
    """

    def __init__(
        self,
        cfg: Optional[EasyTTSRemoteConfig] = None,
        *,
        trust_env: bool = False,
        timeout_sec: int = 300,
    ):
        self.cfg = cfg or load_remote_config()
        self.client = EasyTTSRemoteClient(self.cfg, trust_env=trust_env, timeout_sec=timeout_sec)

    def tts_preset_url(
        self,
        *,
        text: str,
        character: str = "mika",
        preset: str = "普通",
        split_sentence: bool = True,
    ) -> RemoteAudioResult:
        return self.client.tts_preset(character=character, text=text, preset=preset, split_sentence=split_sentence)

    def tts_preset(
        self,
        *,
        text: str,
        character: str = "mika",
        preset: str = "普通",
        split_sentence: bool = True,
    ) -> TTSResult:
        result = self.tts_preset_url(text=text, character=character, preset=preset, split_sentence=split_sentence)
        audio_bytes = self.client.download_audio(result.audio_url)
        return TTSResult(audio_bytes=audio_bytes, audio_url=result.audio_url, orig_name=result.orig_name)

    def tts_upload_url(
        self,
        *,
        text: str,
        reference_audio: Union[str, Path, bytes],
        reference_text: str,
        reference_filename: str = "ref.wav",
        character: str = "mika",
        preset: str = "普通",
        split_sentence: bool = True,
    ) -> RemoteAudioResult:
        if isinstance(reference_audio, (str, Path)):
            p = Path(reference_audio)
            reference_filename = p.name
            audio_bytes = p.read_bytes()
        else:
            audio_bytes = reference_audio

        uploaded_paths = self.client.upload_reference_audio(audio_bytes, reference_filename)
        return self.client.tts_upload_ref(
            character=character,
            text=text,
            preset=preset,
            split_sentence=split_sentence,
            uploaded_paths=uploaded_paths,
            reference_text=reference_text,
            reference_filename=reference_filename,
        )

    def tts_upload(
        self,
        *,
        text: str,
        reference_audio: Union[str, Path, bytes],
        reference_text: str,
        reference_filename: str = "ref.wav",
        character: str = "mika",
        preset: str = "普通",
        split_sentence: bool = True,
    ) -> TTSResult:
        result = self.tts_upload_url(
            text=text,
            reference_audio=reference_audio,
            reference_text=reference_text,
            reference_filename=reference_filename,
            character=character,
            preset=preset,
            split_sentence=split_sentence,
        )
        audio_bytes = self.client.download_audio(result.audio_url)
        return TTSResult(audio_bytes=audio_bytes, audio_url=result.audio_url, orig_name=result.orig_name)

    @staticmethod
    def save(result: TTSResult, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(result.audio_bytes)
        return p


class EasyTTSLocal:
    """
    Local (in-process) TTS interface using `genie_tts`.

    This does NOT call your deployed Gradio app. It runs inference locally, so you
    need the model resources available locally (GenieData + CharacterModels).
    """

    def __init__(
        self,
        *,
        character_version: Optional[str] = None,
        root_dir: Union[str, Path, None] = None,
        auto_download: bool = True,
    ):
        if auto_download:
            os.environ.setdefault("GENIE_AUTO_DOWNLOAD", "1")

        import genie_tts as genie  # local dependency

        self.genie = genie
        self.loaded: set[str] = set()
        self.character_version = character_version or os.getenv("GENIE_CHARACTER_VERSION", "v2ProPlus")
        self.root_dir = Path(root_dir) if root_dir is not None else Path.cwd()

    def _character_dir(self, character: str) -> Path:
        return self.root_dir / "CharacterModels" / self.character_version / character

    def _prompt_wav_json_path(self, character: str) -> Path:
        return self._character_dir(character) / "prompt_wav.json"

    def _load_prompt_wav_json(self, character: str) -> dict:
        path = self._prompt_wav_json_path(character)
        if not path.exists():
            return {}
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    def ensure_character_loaded(self, character: str) -> None:
        if character in self.loaded:
            return
        self.genie.load_predefined_character(character)
        self.loaded.add(character)

    def set_preset_reference(self, *, character: str, preset: str) -> None:
        data = self._load_prompt_wav_json(character)
        item = data.get(preset) if isinstance(data, dict) else None
        if not item:
            raise RuntimeError(f"Unknown preset '{preset}'. Available: {list(data.keys()) if isinstance(data, dict) else []}")

        wav_name = item.get("wav")
        txt = (item.get("text") or "").strip()
        if not wav_name or not txt:
            raise RuntimeError(f"Invalid prompt_wav.json item for preset '{preset}' (need wav+text).")

        audio_path = self._character_dir(character) / "prompt_wav" / wav_name
        if not audio_path.exists():
            raise RuntimeError(f"Missing preset audio: {audio_path}")

        self.genie.set_reference_audio(character_name=character, audio_path=str(audio_path), audio_text=txt)

    def set_upload_reference(
        self,
        *,
        character: str,
        reference_audio: Union[str, Path, bytes],
        reference_text: str,
        reference_filename: str = "ref.wav",
    ) -> None:
        txt = (reference_text or "").strip()
        if not txt:
            raise RuntimeError("reference_text is required for upload reference.")

        if isinstance(reference_audio, (str, Path)):
            audio_path = Path(reference_audio)
            if not audio_path.exists():
                raise RuntimeError(f"reference_audio not found: {audio_path}")
            self.genie.set_reference_audio(character_name=character, audio_path=str(audio_path), audio_text=txt)
            return

        import tempfile

        tmp = Path(tempfile.gettempdir()) / reference_filename
        tmp.write_bytes(reference_audio)
        self.genie.set_reference_audio(character_name=character, audio_path=str(tmp), audio_text=txt)

    def tts_preset(
        self,
        *,
        text: str,
        character: str = "mika",
        preset: str = "普通",
        split_sentence: bool = True,
        out_path: Union[str, Path, None] = None,
    ) -> TTSResult:
        self.ensure_character_loaded(character)
        self.set_preset_reference(character=character, preset=preset)

        out = Path(out_path) if out_path is not None else (self.root_dir / f"out_{character}.wav")
        self.genie.tts(
            character_name=character,
            text=text,
            play=False,
            split_sentence=split_sentence,
            save_path=str(out),
        )
        audio_bytes = out.read_bytes()
        return TTSResult(audio_bytes=audio_bytes, audio_url=str(out), orig_name=out.name)

    def tts_upload(
        self,
        *,
        text: str,
        reference_audio: Union[str, Path, bytes],
        reference_text: str,
        reference_filename: str = "ref.wav",
        character: str = "mika",
        split_sentence: bool = True,
        out_path: Union[str, Path, None] = None,
    ) -> TTSResult:
        self.ensure_character_loaded(character)
        self.set_upload_reference(
            character=character,
            reference_audio=reference_audio,
            reference_text=reference_text,
            reference_filename=reference_filename,
        )

        out = Path(out_path) if out_path is not None else (self.root_dir / f"out_{character}.wav")
        self.genie.tts(
            character_name=character,
            text=text,
            play=False,
            split_sentence=split_sentence,
            save_path=str(out),
        )
        audio_bytes = out.read_bytes()
        return TTSResult(audio_bytes=audio_bytes, audio_url=str(out), orig_name=out.name)
