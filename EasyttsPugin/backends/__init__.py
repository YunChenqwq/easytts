"""
TTS 后端模块（EasyttsPugin）
"""

import sys
sys.dont_write_bytecode = True

from .base import TTSBackendBase, TTSBackendRegistry, TTSResult
from .easytts import EasyTTSBackend

TTSBackendRegistry.register("easytts", EasyTTSBackend)

__all__ = ["TTSBackendBase", "TTSBackendRegistry", "TTSResult", "EasyTTSBackend"]

