"""
Seleccion centralizada de modelo LLM.

Controla que proveedor se usa definiendo MODEL_PROVIDER en .env:

    MODEL_PROVIDER=openrouter        -> llama-3.3-70b-instruct:free via OpenRouter
    MODEL_PROVIDER=openrouter_claude -> claude-sonnet-4.6 (requiere credito)
    MODEL_PROVIDER=huggingface       -> Qwen2.5-7B via HF OpenAI-compatible endpoint
    MODEL_PROVIDER=huggingface_llama -> Llama-3.1-8B via HF (sin function calling nativo)

HuggingFace se conecta al endpoint /v1 (OpenAI-compatible) para que los tool
calls funcionen correctamente con el protocolo que usa ADK/LiteLLM.
"""
import os
from google.adk.models.lite_llm import LiteLlm

_DEFAULT_PROVIDER = "openrouter"

# HF serverless inference — endpoint OpenAI-compatible por modelo
_HF_API_BASE = "https://api-inference.huggingface.co/v1"

_HF_MODELS = {
    "huggingface": "Qwen/Qwen2.5-7B-Instruct",
    "huggingface_llama": "meta-llama/Llama-3.1-8B-Instruct",
}


def get_model(num_retries: int = 3) -> LiteLlm:
    provider = os.getenv("MODEL_PROVIDER", _DEFAULT_PROVIDER).lower().strip()
    hf_key = os.getenv("HUGGINGFACE_API_KEY", "")

    if provider == "openrouter":
        model = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
        print(f"[FactorBridge] Proveedor: {provider} | Modelo: {model}")
        return LiteLlm(model=model, num_retries=num_retries)

    if provider == "openrouter_claude":
        model = "openrouter/anthropic/claude-sonnet-4.6"
        print(f"[FactorBridge] Proveedor: {provider} | Modelo: {model}")
        return LiteLlm(model=model, num_retries=num_retries)

    if provider in _HF_MODELS:
        hf_model_id = _HF_MODELS[provider]
        litellm_model = f"huggingface/{hf_model_id}"
        print(f"[FactorBridge] Proveedor: {provider} | Modelo: {hf_model_id}")
        return LiteLlm(
            model=litellm_model,
            api_key=hf_key,
            num_retries=num_retries,
        )

    raise ValueError(
        f"MODEL_PROVIDER='{provider}' no reconocido. "
        f"Valores validos: openrouter, openrouter_claude, huggingface, huggingface_llama"
    )