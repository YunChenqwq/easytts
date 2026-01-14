from __future__ import annotations

from dataclasses import dataclass
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
