"""
文件操作工具（参考 tts_voice_plugin）。
"""

import asyncio
import base64
import os
import tempfile
import uuid
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("easytts_file_manager")

MIN_AUDIO_SIZE = 100


class TTSFileManager:
    _temp_dir: Optional[str] = None
    _project_root: Optional[str] = None

    @classmethod
    def get_project_root(cls) -> str:
        if cls._project_root is None:
            current_file = os.path.abspath(__file__)
            cls._project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
        return cls._project_root

    @classmethod
    def resolve_path(cls, path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(cls.get_project_root(), path)

    @classmethod
    def ensure_dir(cls, dir_path: str) -> bool:
        try:
            os.makedirs(dir_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"ensure_dir failed: {dir_path}: {e}")
            return False

    @classmethod
    def get_temp_dir(cls) -> str:
        if cls._temp_dir is None:
            cls._temp_dir = tempfile.gettempdir()
        return cls._temp_dir

    @classmethod
    def generate_temp_path(cls, prefix: str = "tts", suffix: str = ".wav", output_dir: str = "") -> str:
        if not output_dir:
            resolved_dir = cls.get_project_root()
        else:
            resolved_dir = cls.resolve_path(output_dir)
            if not cls.ensure_dir(resolved_dir):
                resolved_dir = cls.get_project_root()
        filename = f"{prefix}_{uuid.uuid4().hex[:12]}{suffix}"
        return os.path.join(resolved_dir, filename)

    @staticmethod
    def _write_file_sync(path: str, data: bytes):
        with open(path, "wb") as f:
            f.write(data)

    @classmethod
    async def write_audio_async(cls, path: str, data: bytes) -> bool:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, cls._write_file_sync, path, data)
            return True
        except Exception as e:
            logger.error(f"write_audio_async failed: {path}: {e}")
            return False

    @classmethod
    async def cleanup_file_async(cls, path: str, delay: float = 0) -> bool:
        if delay > 0:
            await asyncio.sleep(delay)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, cls.cleanup_file, path, True)

    @classmethod
    def cleanup_file(cls, path: str, silent: bool = True) -> bool:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                return True
            return False
        except Exception as e:
            if not silent:
                logger.warning(f"cleanup_file failed: {path}: {e}")
            return False

    @classmethod
    def validate_audio_data(cls, data: bytes, min_size: int = None) -> tuple[bool, str]:
        if data is None:
            return False, "音频数据为空"
        min_size = min_size or MIN_AUDIO_SIZE
        if len(data) < min_size:
            return False, f"音频数据过小({len(data)} < {min_size})"
        return True, ""

    @classmethod
    def audio_to_base64(cls, data: bytes) -> str:
        try:
            return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.error(f"audio_to_base64 failed: {e}")
            return ""

