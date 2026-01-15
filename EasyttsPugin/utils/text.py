"""
文本处理工具（参考 tts_voice_plugin）。
"""

import re
from typing import List, Optional


class TTSTextUtils:
    CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    ENGLISH_PATTERN = re.compile(r"[a-zA-Z]")
    JAPANESE_PATTERN = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

    @classmethod
    def clean_text(cls, text: str, max_length: int = 500) -> str:
        if not text:
            return ""
        return text.strip()

    @classmethod
    def detect_language(cls, text: str) -> str:
        if not text:
            return "zh"
        chinese_chars = len(cls.CHINESE_PATTERN.findall(text))
        english_chars = len(cls.ENGLISH_PATTERN.findall(text))
        japanese_chars = len(cls.JAPANESE_PATTERN.findall(text))
        total = chinese_chars + english_chars + japanese_chars
        if total == 0:
            return "zh"
        if chinese_chars / total > 0.3:
            return "zh"
        if japanese_chars / total > 0.3:
            return "ja"
        if english_chars / total > 0.8:
            return "en"
        return "zh"

    @classmethod
    def resolve_voice_alias(cls, voice: Optional[str], alias_map: dict, default: str, prefix: str = "") -> str:
        if not voice:
            voice = default
        if prefix and voice.startswith(prefix):
            return voice
        if voice in alias_map:
            return alias_map[voice]
        if default in alias_map:
            return alias_map[default]
        return default

    @classmethod
    def split_sentences(cls, text: str, min_length: int = 2) -> List[str]:
        if not text:
            return []
        pattern = r"([。！!？?；;])"
        parts = re.split(pattern, text)
        sentences: List[str] = []
        current = ""
        for part in parts:
            if not part:
                continue
            if re.match(pattern, part):
                current += part
            else:
                if current.strip():
                    sentences.append(current.strip())
                current = part
        if current.strip():
            sentences.append(current.strip())
        if min_length > 0 and len(sentences) > 1:
            merged: List[str] = []
            for sent in sentences:
                if merged and len(sent) < min_length:
                    merged[-1] += sent
                else:
                    merged.append(sent)
            sentences = merged
        return sentences

