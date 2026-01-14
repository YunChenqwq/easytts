"""
Centralized configuration for the remote Gradio app API.

Secret handling:
- Do NOT hardcode real tokens in git.
- Prefer environment variables in production.
- For local development, you can create `easytts_secrets.py` (gitignored) and put
  your token there; this module will read it first, then fall back to env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EasyTTSRemoteConfig:
    base_url: str
    studio_token: str
    fn_index: int
    trigger_id: int


def load_remote_config() -> EasyTTSRemoteConfig:
    """
    Loads configuration from `easytts_secrets.py` (if present) and environment variables.

    Required:
    - EASYTTS_STUDIO_TOKEN: ModelScope studio_token (treat as secret)

    Optional:
    - EASYTTS_BASE_URL: default https://yunchenqwq-easytts.ms.show
    - EASYTTS_FN_INDEX: default 3
    - EASYTTS_TRIGGER_ID: default 19
    """

    secrets: dict[str, object] = {}
    try:
        import easytts_secrets as _secrets  # type: ignore
    except ImportError:
        _secrets = None

    if _secrets is not None:
        secrets = {
            "base_url": getattr(_secrets, "EASYTTS_BASE_URL", None),
            "studio_token": getattr(_secrets, "EASYTTS_STUDIO_TOKEN", None),
            "fn_index": getattr(_secrets, "EASYTTS_FN_INDEX", None),
            "trigger_id": getattr(_secrets, "EASYTTS_TRIGGER_ID", None),
        }

    base_url = str(secrets.get("base_url") or os.getenv("EASYTTS_BASE_URL", "https://yunchenqwq-easytts.ms.show")).rstrip("/")
    studio_token = str(secrets.get("studio_token") or os.getenv("EASYTTS_STUDIO_TOKEN", "")).strip()
    if not studio_token:
        raise RuntimeError(
            "Missing studio token. Set EASYTTS_STUDIO_TOKEN or fill EASYTTS_STUDIO_TOKEN in easytts_secrets.py."
        )

    fn_index = int(secrets.get("fn_index") or os.getenv("EASYTTS_FN_INDEX", "3"))
    trigger_id = int(secrets.get("trigger_id") or os.getenv("EASYTTS_TRIGGER_ID", "19"))
    return EasyTTSRemoteConfig(
        base_url=base_url,
        studio_token=studio_token,
        fn_index=fn_index,
        trigger_id=trigger_id,
    )

