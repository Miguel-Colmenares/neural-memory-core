"""Cliente mínimo para modelos de lenguaje con API compatible con OpenAI.

Es opcional. Sin configurar, el sistema responde de forma extractiva.
ADVERTENCIA: un proveedor en la nube puede tener costo y recibe los
fragmentos de recuerdos usados como contexto.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from core.config import Settings, get_settings


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        api_base: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self._url = api_base.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._transport = transport

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(self._url, json=payload, headers=self._headers)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise LLMError(f"Fallo del modelo de lenguaje: {exc}") from exc


def build_llm(settings: Settings) -> LLMClient | None:
    if settings.llm_provider == "none" or not settings.llm_model:
        return None
    return LLMClient(
        api_base=settings.llm_api_base,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )


@lru_cache
def get_llm() -> LLMClient | None:
    return build_llm(get_settings())
