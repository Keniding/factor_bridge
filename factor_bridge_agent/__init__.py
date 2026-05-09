"""FactorBridge Agent — Intermediario bilateral de factoring para Peru."""
import asyncio
import re
import litellm
from litellm import acompletion as _litellm_acompletion
from google.adk.models.lite_llm import LiteLLMClient

# --- Retry patch ---------------------------------------------------------
# litellm.acompletion reintenta en 429 pero sin esperar entre intentos.
# Este patch reemplaza LiteLLMClient.acompletion con una version que
# duerme el tiempo real del header Retry-After antes de cada reintento.

_MAX_RETRIES = 8
_FALLBACK_WAIT = 15  # segundos si no hay Retry-After en la respuesta


async def _acompletion_with_backoff(self, model, messages, tools, **kwargs):
    kwargs.pop("num_retries", None)  # desactiva reintentos inmediatos de litellm
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await _litellm_acompletion(
                model=model, messages=messages, tools=tools, **kwargs
            )
        except litellm.RateLimitError as exc:
            if attempt == _MAX_RETRIES:
                raise
            match = re.search(r'"retry_after_seconds":\s*(\d+)', str(exc))
            wait = int(match.group(1)) + 2 if match else _FALLBACK_WAIT * (2 ** attempt)
            print(
                f"\n[FactorBridge] 429 rate limit — reintentando en {wait}s "
                f"(intento {attempt + 1}/{_MAX_RETRIES})\n"
            )
            await asyncio.sleep(wait)


LiteLLMClient.acompletion = _acompletion_with_backoff
# -------------------------------------------------------------------------

from . import agent  # noqa: E402

__all__ = ["agent"]
