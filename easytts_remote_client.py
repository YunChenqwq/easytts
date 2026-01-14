from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from easytts_tokens import EasyTTSRemoteConfig


@dataclass(frozen=True)
class RemoteAudioResult:
    audio_url: str
    file_path: Optional[str] = None
    orig_name: Optional[str] = None


class EasyTTSRemoteClient:
    """
    Remote client that talks to a deployed ModelScope Studio Gradio app via:
    - POST /gradio_api/upload
    - POST /gradio_api/queue/join
    - GET  /gradio_api/queue/data (SSE)
    - GET  /gradio_api/file=...
    """

    def __init__(self, cfg: EasyTTSRemoteConfig, *, trust_env: bool = False, timeout_sec: int = 300):
        self.cfg = cfg
        self.timeout_sec = timeout_sec
        self.session = requests.Session()
        self.session.trust_env = trust_env
        self.data_type = ["dropdown", "textbox", "checkbox", "radio", "dropdown", "audio", "textbox"]

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Studio-Token": self.cfg.studio_token,
            "X-Gradio-User": "app",
        }

    def _cookies(self) -> Dict[str, str]:
        return {"studio_token": self.cfg.studio_token}

    def upload_reference_audio(self, file_bytes: bytes, filename: str) -> List[str]:
        upload_id = uuid.uuid4().hex[:10]
        url = f"{self.cfg.base_url}/gradio_api/upload?upload_id={upload_id}"
        headers = {"X-Studio-Token": self.cfg.studio_token}
        files = {"files": (filename, file_bytes)}
        resp = self.session.post(url, headers=headers, cookies=self._cookies(), files=files, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], str):
            raise RuntimeError(f"Unexpected upload response: {data}")
        return data

    def tts_preset(
        self,
        *,
        character: str,
        text: str,
        preset: str = "普通",
        split_sentence: bool = True,
    ) -> RemoteAudioResult:
        payload = {
            "fn_index": self.cfg.fn_index,
            "trigger_id": self.cfg.trigger_id,
            "session_hash": uuid.uuid4().hex[:11],
            "dataType": self.data_type,
            "data": [character, text, split_sentence, "preset", preset, None, None],
        }
        return self._submit_and_wait(payload)

    def tts_upload_ref(
        self,
        *,
        character: str,
        text: str,
        preset: str = "普通",
        split_sentence: bool = True,
        uploaded_paths: List[str],
        reference_text: str,
    ) -> RemoteAudioResult:
        payload = {
            "fn_index": self.cfg.fn_index,
            "trigger_id": self.cfg.trigger_id,
            "session_hash": uuid.uuid4().hex[:11],
            "dataType": self.data_type,
            "data": [character, text, split_sentence, "upload", preset, uploaded_paths, reference_text],
        }
        return self._submit_and_wait(payload)

    def download_audio(self, audio_url: str) -> bytes:
        resp = self.session.get(
            audio_url, headers={"X-Studio-Token": self.cfg.studio_token}, cookies=self._cookies(), timeout=120
        )
        resp.raise_for_status()
        return resp.content

    def _submit_and_wait(self, payload: Dict[str, Any]) -> RemoteAudioResult:
        join_url = (
            f"{self.cfg.base_url}/gradio_api/queue/join"
            f"?t={int(time.time() * 1000)}&__theme=light&backend_url=%2F&studio_token={self.cfg.studio_token}"
        )

        join_resp = self.session.post(
            join_url,
            headers=self._headers(),
            cookies=self._cookies(),
            json=payload,
            timeout=30,
        )
        join_resp.raise_for_status()

        session_hash = payload["session_hash"]
        data_url = f"{self.cfg.base_url}/gradio_api/queue/data?session_hash={session_hash}&studio_token={self.cfg.studio_token}"

        audio_url: Optional[str] = None
        file_path: Optional[str] = None
        orig_name: Optional[str] = None

        with self.session.get(
            data_url,
            headers={"Accept": "text/event-stream", "X-Studio-Token": self.cfg.studio_token},
            cookies=self._cookies(),
            stream=True,
            timeout=self.timeout_sec,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                evt = json.loads(raw[5:].strip())
                if evt.get("msg") != "process_completed":
                    continue
                out = (evt.get("output") or {}).get("data") or []
                if not out:
                    raise RuntimeError(f"process_completed but output.data is empty: {evt}")
                picked = self._pick_output_audio(out)
                if isinstance(picked, dict):
                    file_path = picked.get("path")
                    orig_name = picked.get("orig_name")
                    audio_url = picked.get("url") or None
                    if not audio_url:
                        if isinstance(file_path, str) and file_path.startswith("/tmp/"):
                            audio_url = f"{self.cfg.base_url}/gradio_api/file={file_path}"
                        elif isinstance(file_path, str) and file_path.startswith("/gradio_api/"):
                            audio_url = f"{self.cfg.base_url}{file_path}"
                elif isinstance(picked, str):
                    audio_url = picked
                else:
                    raise RuntimeError(f"Unexpected picked output type: {type(picked)}")
                break

        if not audio_url:
            raise RuntimeError("No audio URL returned from queue/data SSE.")

        if audio_url.startswith("/"):
            audio_url = f"{self.cfg.base_url}{audio_url}"

        return RemoteAudioResult(audio_url=audio_url, file_path=file_path, orig_name=orig_name)

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

        if best_idx >= 0:
            return out[best_idx]
        return out[-1]
