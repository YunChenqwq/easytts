from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.common.logger import get_logger

from ..config_keys import ConfigKeys
from ..utils.file import TTSFileManager
from ..utils.session import TTSSessionManager
from .base import TTSBackendBase, TTSResult

logger = get_logger("easytts_backend.easytts")


@dataclass(frozen=True)
class EasyTTSEndpoint:
    name: str
    base_url: str
    studio_token: str
    fn_index: int
    trigger_id: int

    @property
    def key(self) -> str:
        return f"{self.base_url}|{self.studio_token}|{self.fn_index}|{self.trigger_id}"


class EasyTTSBackend(TTSBackendBase):
    backend_name = "easytts"
    backend_description = "EasyTTS（ModelScope Studio / Gradio）后端 + 云端仓库池自动切换"
    default_audio_format = "wav"

    _endpoint_locks: Dict[str, asyncio.Lock] = {}
    _locks_guard = asyncio.Lock()

    def __init__(self, config_getter, log_prefix: str = ""):
        super().__init__(config_getter, log_prefix)
        self._data_type = ["dropdown", "textbox", "checkbox", "radio", "dropdown", "audio", "textbox"]

    def validate_config(self) -> Tuple[bool, str]:
        endpoints = self._load_endpoints()
        if not endpoints:
            return False, "easytts.endpoints 为空，请至少配置一个云端仓库"
        for ep in endpoints:
            if not ep.base_url or not ep.studio_token:
                return False, "easytts.endpoints 中 base_url / studio_token 不能为空"
        return True, ""

    def _load_endpoints(self) -> List[EasyTTSEndpoint]:
        raw = self.get_config(ConfigKeys.EASYTTS_ENDPOINTS, []) or []
        endpoints: List[EasyTTSEndpoint] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            base_url = str(item.get("base_url", "")).rstrip("/")
            studio_token = str(item.get("studio_token", "")).strip()
            name = str(item.get("name", f"endpoint-{idx}")).strip() or f"endpoint-{idx}"
            fn_index = int(item.get("fn_index", 3) or 3)
            trigger_id = int(item.get("trigger_id", 19) or 19)
            if base_url:
                endpoints.append(
                    EasyTTSEndpoint(
                        name=name,
                        base_url=base_url,
                        studio_token=studio_token,
                        fn_index=fn_index,
                        trigger_id=trigger_id,
                    )
                )
        return endpoints

    async def _get_or_create_lock(self, key: str) -> asyncio.Lock:
        async with self._locks_guard:
            if key not in self._endpoint_locks:
                self._endpoint_locks[key] = asyncio.Lock()
            return self._endpoint_locks[key]

    def _headers(self, token: str, *, json_content: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-Studio-Token": token,
            "X-Gradio-User": "app",
            "Cookie": f"studio_token={token}",
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    async def _get_queue_size(self, ep: EasyTTSEndpoint) -> Optional[int]:
        status_url = f"{ep.base_url}/gradio_api/queue/status"
        status_timeout = int(self.get_config(ConfigKeys.EASYTTS_STATUS_TIMEOUT, 3) or 3)
        trust_env = bool(self.get_config(ConfigKeys.EASYTTS_TRUST_ENV, False))
        session_manager = await TTSSessionManager.get_instance(trust_env=trust_env)
        try:
            async with session_manager.get(
                status_url,
                headers={"X-Studio-Token": ep.studio_token, "Cookie": f"studio_token={ep.studio_token}"},
                backend_name=f"easytts:{ep.name}",
                timeout=status_timeout,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                qs = data.get("queue_size")
                return qs if isinstance(qs, int) else None
        except Exception:
            return None

    async def _sorted_endpoints(self, endpoints: List[EasyTTSEndpoint]) -> List[EasyTTSEndpoint]:
        prefer_idle = bool(self.get_config(ConfigKeys.EASYTTS_PREFER_IDLE_ENDPOINT, True))
        busy_threshold = int(self.get_config(ConfigKeys.EASYTTS_BUSY_QUEUE_THRESHOLD, 0) or 0)

        sizes: List[Tuple[EasyTTSEndpoint, int]] = []
        for ep in endpoints:
            qs = await self._get_queue_size(ep)
            sizes.append((ep, qs if isinstance(qs, int) else 10_000))

        sizes.sort(key=lambda x: (x[1], x[0].name))
        if not prefer_idle:
            return [ep for ep, _ in sizes]
        idle = [ep for ep, qs in sizes if qs <= busy_threshold]
        busy = [ep for ep, qs in sizes if qs > busy_threshold]
        return idle + busy

    def _parse_voice(self, voice: Optional[str]) -> Tuple[str, str, str, bool]:
        default_character = self.get_config(ConfigKeys.EASYTTS_DEFAULT_CHARACTER, "mika")
        default_preset = self.get_config(ConfigKeys.EASYTTS_DEFAULT_PRESET, "普通")
        raw = (voice or "").strip()
        if not raw:
            return default_character, default_preset, f"{default_character}:{default_preset}", False
        if ":" in raw:
            character, preset = raw.split(":", 1)
            character = character.strip() or default_character
            preset = preset.strip() or default_preset
            return character, preset, f"{character}:{preset}", True
        # voice 只给了 character，没有给 preset：视为未显式指定 preset，允许 emotion 覆盖
        return raw, default_preset, f"{raw}:{default_preset}", False

    def _load_emotion_map(self) -> Dict[str, str]:
        raw = self.get_config(ConfigKeys.EASYTTS_EMOTION_PRESET_MAP, {}) or {}
        if isinstance(raw, dict):
            return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip() and str(v).strip()}
        # 兼容 list[{"emotion": "...", "preset": "..."}]
        if isinstance(raw, list):
            out: Dict[str, str] = {}
            for item in raw:
                if not isinstance(item, dict):
                    continue
                k = str(item.get("emotion", "")).strip()
                v = str(item.get("preset", "")).strip()
                if k and v:
                    out[k] = v
            return out
        return {}

    def _load_character_emotion_map(self, character: str) -> Dict[str, str]:
        chars = self.get_config(ConfigKeys.EASYTTS_CHARACTERS, []) or []
        if not isinstance(chars, list):
            return {}
        for item in chars:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).strip() != character:
                continue
            raw = item.get("emotion_preset_map") or {}
            if isinstance(raw, dict):
                return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip() and str(v).strip()}
        return {}

    def _resolve_preset_by_emotion(self, *, character: str, preset: str, emotion: str, explicit_preset: bool) -> str:
        emo = (emotion or "").strip()
        if not emo or explicit_preset:
            return preset

        # 角色级映射优先
        char_map = self._load_character_emotion_map(character)
        if emo in char_map:
            return char_map[emo]

        # 全局映射
        global_map = self._load_emotion_map()
        if emo in global_map:
            return global_map[emo]

        # 常见同义：把 “难过/悲伤” 映射到 “伤心” 等（仅在用户没配置时兜底）
        if "伤心" in global_map and emo in ("难过", "悲伤"):
            return global_map["伤心"]
        if "开心" in global_map and emo in ("高兴", "兴奋"):
            return global_map["开心"]

        return preset

    def _pick_output_audio(self, out: List[Any]) -> Any:
        best_idx = -1
        best_score = -1
        for idx, item in enumerate(out):
            s = ""
            if isinstance(item, dict):
                s = " ".join(str(x or "") for x in (item.get("orig_name"), item.get("path"), item.get("url")))
            elif isinstance(item, str):
                s = item
            else:
                continue
            score = 0
            if "genie_" in s:
                score += 10
            if ".wav" in s.lower():
                score += 2
            if "/tmp/gradio" in s:
                score += 1
            if score > best_score or (score == best_score and idx > best_idx):
                best_score = score
                best_idx = idx
        return out[best_idx] if best_idx >= 0 else out[-1]

    async def _synthesize_on_endpoint(
        self,
        ep: EasyTTSEndpoint,
        *,
        text: str,
        character: str,
        preset: str,
        split_sentence: bool,
    ) -> bytes:
        join_timeout = int(self.get_config(ConfigKeys.EASYTTS_JOIN_TIMEOUT, 30) or 30)
        sse_timeout = int(self.get_config(ConfigKeys.EASYTTS_SSE_TIMEOUT, 300) or 300)
        download_timeout = int(self.get_config(ConfigKeys.EASYTTS_DOWNLOAD_TIMEOUT, 120) or 120)
        trust_env = bool(self.get_config(ConfigKeys.EASYTTS_TRUST_ENV, False))

        payload: Dict[str, Any] = {
            "fn_index": ep.fn_index,
            "trigger_id": ep.trigger_id,
            "session_hash": uuid.uuid4().hex[:11],
            "dataType": self._data_type,
            "data": [character, text, split_sentence, "preset", preset, None, None],
        }

        join_url = (
            f"{ep.base_url}/gradio_api/queue/join"
            f"?t={int(time.time() * 1000)}&__theme=light&backend_url=%2F&studio_token={ep.studio_token}"
        )
        data_url = f"{ep.base_url}/gradio_api/queue/data?session_hash={payload['session_hash']}&studio_token={ep.studio_token}"

        session_manager = await TTSSessionManager.get_instance(trust_env=trust_env)

        async with session_manager.post(
            join_url,
            json=payload,
            headers=self._headers(ep.studio_token, json_content=True),
            backend_name=f"easytts:{ep.name}",
            timeout=join_timeout,
        ) as join_resp:
            if join_resp.status != 200:
                body = await join_resp.text()
                raise RuntimeError(f"queue/join failed: {join_resp.status} {body[:200]}")

        audio_url: Optional[str] = None
        file_path: Optional[str] = None

        async with session_manager.get(
            data_url,
            headers={"Accept": "text/event-stream", "X-Studio-Token": ep.studio_token, "Cookie": f"studio_token={ep.studio_token}"},
            backend_name=f"easytts:{ep.name}",
            timeout=sse_timeout,
        ) as data_resp:
            if data_resp.status != 200:
                body = await data_resp.text()
                raise RuntimeError(f"queue/data failed: {data_resp.status} {body[:200]}")

            buffer = ""
            async for chunk in data_resp.content.iter_chunked(4096):
                if not chunk:
                    continue
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        evt = json.loads(data_str)
                    except Exception:
                        continue
                    if evt.get("msg") != "process_completed":
                        continue
                    if not evt.get("success", True):
                        raise RuntimeError(f"process_completed but success=false: {evt}")
                    out = (evt.get("output") or {}).get("data") or []
                    if not out:
                        raise RuntimeError(f"process_completed but output.data empty: {evt}")
                    picked = self._pick_output_audio(out)
                    if isinstance(picked, dict):
                        file_path = picked.get("path")
                        audio_url = picked.get("url") or None
                        if not audio_url and isinstance(file_path, str):
                            if file_path.startswith("/tmp/"):
                                audio_url = f"{ep.base_url}/gradio_api/file={file_path}"
                            elif file_path.startswith("/"):
                                audio_url = f"{ep.base_url}{file_path}"
                    elif isinstance(picked, str):
                        audio_url = picked
                    break
                if audio_url:
                    break

        if not audio_url:
            raise RuntimeError("No audio url returned from SSE.")
        if audio_url.startswith("/"):
            audio_url = f"{ep.base_url}{audio_url}"

        async with session_manager.get(
            audio_url,
            headers={"X-Studio-Token": ep.studio_token, "Cookie": f"studio_token={ep.studio_token}"},
            backend_name=f"easytts:{ep.name}",
            timeout=download_timeout,
        ) as dl_resp:
            if dl_resp.status != 200:
                body = await dl_resp.text()
                raise RuntimeError(f"download failed: {dl_resp.status} {body[:200]}")
            audio_bytes = await dl_resp.read()
            ok, err = TTSFileManager.validate_audio_data(audio_bytes)
            if not ok:
                raise RuntimeError(f"invalid audio data: {err}")
            return audio_bytes

    async def execute(self, text: str, voice: Optional[str] = None, **kwargs) -> TTSResult:
        ok, err = self.validate_config()
        if not ok:
            return TTSResult(False, err, backend_name=self.backend_name)

        emotion = str(kwargs.get("emotion", "") or "").strip()
        character, preset, voice_info, explicit_preset = self._parse_voice(voice)
        preset = self._resolve_preset_by_emotion(
            character=character,
            preset=preset,
            emotion=emotion,
            explicit_preset=explicit_preset,
        )
        voice_info = f"{character}:{preset}"
        remote_split = bool(self.get_config(ConfigKeys.EASYTTS_REMOTE_SPLIT_SENTENCE, True))

        endpoints = self._load_endpoints()
        ordered = await self._sorted_endpoints(endpoints)

        last_error: Optional[str] = None
        for ep in ordered:
            lock = await self._get_or_create_lock(ep.key)
            if lock.locked():
                continue
            async with lock:
                try:
                    logger.info(f"{self.log_prefix} use endpoint={ep.name} {voice_info}")
                    audio_bytes = await self._synthesize_on_endpoint(
                        ep,
                        text=text,
                        character=character,
                        preset=preset,
                        split_sentence=remote_split,
                    )
                    return await self.send_audio(audio_bytes, audio_format="wav", prefix="tts", voice_info=voice_info)
                except Exception as e:
                    last_error = f"{ep.name}: {e}"
                    logger.warning(f"{self.log_prefix} endpoint failed: {last_error}")
                    continue

        return TTSResult(False, f"所有云端仓库均失败：{last_error or 'unknown error'}", backend_name=self.backend_name)
