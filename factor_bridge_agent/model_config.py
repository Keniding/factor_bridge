"""
Seleccion centralizada de modelo LLM.

Controla que proveedor se usa definiendo MODEL_PROVIDER en .env:

    MODEL_PROVIDER=openrouter   -> meta-llama/llama-3.3-70b-instruct:free (default)
    MODEL_PROVIDER=openrouter_claude -> anthropic/claude-sonnet-4.6 (requiere credito)
    MODEL_PROVIDER=huggingface  -> meta-llama/Meta-Llama-3.1-8B-Instruct (gratis, HF token)

El retry con backoff real se aplica en __init__.py y funciona para todos los proveedores.
"""
import os
from google.adk.models.lite_llm import LiteLlm

_MODELS = {
    "openrouter": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter_claude": "openrouter/anthropic/claude-sonnet-4.6",
    "huggingface": "huggingface/meta-llama/Llama-3.1-8B-Instruct",  # tambien: Qwen/Qwen2.5-7B-Instruct
}

_DEFAULT_PROVIDER = "openrouter"


def get_model(num_retries: int = 6) -> LiteLlm:
    provider = os.getenv("MODEL_PROVIDER", _DEFAULT_PROVIDER).lower().strip()
    model = _MODELS.get(provider)
    if model is None:
        raise ValueError(
            f"MODEL_PROVIDER='{provider}' no reconocido. "
            f"Valores validos: {list(_MODELS)}"
        )
    print(f"[FactorBridge] Proveedor: {provider} | Modelo: {model}")
    return LiteLlm(model=model, num_retries=num_retries)
