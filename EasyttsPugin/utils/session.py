"""
HTTP Session 管理器（参考 tts_voice_plugin）。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import aiohttp
from src.common.logger import get_logger

logger = get_logger("easytts_session_manager")


class TTSSessionManager:
    _instance: Optional["TTSSessionManager"] = None
    _lock = asyncio.Lock()

    def __init__(self, *, trust_env: bool = False):
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._default_timeout = 60
        self._trust_env = trust_env

    @classmethod
    async def get_instance(cls, *, trust_env: bool = False) -> "TTSSessionManager":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(trust_env=trust_env)
        else:
            cls._instance._trust_env = trust_env
        return cls._instance

    async def get_session(self, backend_name: str = "default", timeout: int = None) -> aiohttp.ClientSession:
        if backend_name not in self._sessions or self._sessions[backend_name].closed:
            timeout_val = timeout or self._default_timeout
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
                force_close=True,
            )
            self._sessions[backend_name] = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout_val),
                trust_env=self._trust_env,
            )
            logger.debug(f"create session: {backend_name} trust_env={self._trust_env}")
        return self._sessions[backend_name]

    @asynccontextmanager
    async def post(
        self,
        url: str,
        json: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        data: Any = None,
        backend_name: str = "default",
        timeout: int = None,
    ):
        session = await self.get_session(backend_name, timeout)
        req_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        resp = await session.post(url, json=json, headers=headers, data=data, timeout=req_timeout)
        try:
            yield resp
        finally:
            resp.release()

    @asynccontextmanager
    async def get(
        self,
        url: str,
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        backend_name: str = "default",
        timeout: int = None,
    ):
        session = await self.get_session(backend_name, timeout)
        req_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        resp = await session.get(url, headers=headers, params=params, timeout=req_timeout)
        try:
            yield resp
        finally:
            resp.release()

    async def close_session(self, backend_name: str = None):
        if backend_name:
            session = self._sessions.pop(backend_name, None)
            if session and not session.closed:
                await session.close()
        else:
            for session in self._sessions.values():
                if not session.closed:
                    await session.close()
            self._sessions.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()

