"""
TTS 后端抽象基类与注册表（参考 tts_voice_plugin）
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.common.logger import get_logger

from ..config_keys import ConfigKeys

logger = get_logger("easytts_backend")


@dataclass
class TTSResult:
    success: bool
    message: str
    audio_path: Optional[str] = None
    backend_name: str = ""

    def __iter__(self):
        return iter((self.success, self.message))


class TTSBackendBase(ABC):
    backend_name: str = "base"
    backend_description: str = "TTS 后端基类"
    support_private_chat: bool = True
    default_audio_format: str = "wav"

    def __init__(self, config_getter: Callable[[str, Any], Any], log_prefix: str = ""):
        self.get_config = config_getter
        self.log_prefix = log_prefix or f"[{self.backend_name}]"
        self._send_custom = None

    def set_send_custom(self, send_custom_func: Callable) -> None:
        self._send_custom = send_custom_func

    async def send_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        prefix: str = "tts",
        voice_info: str = "",
    ) -> TTSResult:
        from ..utils.file import TTSFileManager

        use_base64 = self.get_config(ConfigKeys.GENERAL_USE_BASE64_AUDIO, True)

        if use_base64:
            base64_audio = TTSFileManager.audio_to_base64(audio_data)
            if not base64_audio:
                return TTSResult(False, "音频转 base64 失败", backend_name=self.backend_name)
            if not self._send_custom:
                return TTSResult(False, "send_custom 未设置", backend_name=self.backend_name)
            await self._send_custom(message_type="voice", content=base64_audio)
            return TTSResult(
                True,
                f"已发送 {self.backend_name} 语音{(' ('+voice_info+')') if voice_info else ''}（base64）",
                backend_name=self.backend_name,
            )

        output_dir = self.get_config(ConfigKeys.GENERAL_AUDIO_OUTPUT_DIR, "")
        audio_path = TTSFileManager.generate_temp_path(prefix=prefix, suffix=f".{audio_format}", output_dir=output_dir)
        if not await TTSFileManager.write_audio_async(audio_path, audio_data):
            return TTSResult(False, "保存音频文件失败", backend_name=self.backend_name)
        if not self._send_custom:
            return TTSResult(False, "send_custom 未设置", backend_name=self.backend_name)
        await self._send_custom(message_type="voiceurl", content=audio_path)
        asyncio.create_task(TTSFileManager.cleanup_file_async(audio_path, delay=30))
        return TTSResult(
            True,
            f"已发送 {self.backend_name} 语音{(' ('+voice_info+')') if voice_info else ''}",
            audio_path=audio_path,
            backend_name=self.backend_name,
        )

    @abstractmethod
    async def execute(self, text: str, voice: Optional[str] = None, **kwargs) -> TTSResult:
        raise NotImplementedError

    def validate_config(self) -> Tuple[bool, str]:
        return True, ""

    def is_available(self) -> bool:
        ok, _ = self.validate_config()
        return ok


class TTSBackendRegistry:
    _backends: Dict[str, Type[TTSBackendBase]] = {}

    @classmethod
    def register(cls, name: str, backend_class: Type[TTSBackendBase]) -> None:
        cls._backends[name] = backend_class
        logger.debug(f"register backend: {name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[TTSBackendBase]]:
        return cls._backends.get(name)

    @classmethod
    def create(cls, name: str, config_getter: Callable[[str, Any], Any], log_prefix: str = "") -> Optional[TTSBackendBase]:
        backend_class = cls.get(name)
        if not backend_class:
            return None
        return backend_class(config_getter, log_prefix)

