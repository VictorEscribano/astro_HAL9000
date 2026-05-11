"""CPU LLM model registry for HAL9000.

Catalogues the Pareto frontier of speed vs quality for CPU-only inference.
Each entry lists the HuggingFace model ID, quantization, expected performance,
and which backend (llamacpp / onnx) best serves it.

Usage:
    from app.services.model_registry import REGISTRY, recommend
    rec = recommend(ram_gb=8, cores=8, priority="balanced")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


BackendType = Literal["llamacpp", "onnx", "ollama", "ik_llama"]


@dataclass
class ModelProfile:
    id: str                          # short key used in .env MODEL_PROFILE=...
    name: str                        # human-readable display name
    hf_repo: str                     # HuggingFace repo (or GGUF repo)
    hf_filename: str | None          # specific GGUF file within repo, None for ONNX dirs
    backend: BackendType
    quant: str                       # e.g. "Q4_K_M", "INT4", "Q8_0"
    params_b: float                  # total parameter count (billions)
    active_params_b: float           # active params per token (equals params_b for dense)
    ram_gb: float                    # approximate RAM required
    tok_per_sec_8core: float         # expected tokens/s on 8-core modern CPU
    ctx_k: int                       # context window in thousands of tokens
    thinking_mode: bool              # supports <think>…</think> chain-of-thought
    multilingual: bool
    astronomy_specialist: bool       # fine-tuned on astronomy data
    notes: str = ""
    download_cmd: str = ""           # one-liner to download this model

    @property
    def is_moe(self) -> bool:
        return self.active_params_b < self.params_b * 0.5


# ── Registry ──────────────────────────────────────────────────────────────────
#
# Ordered roughly from fastest to highest quality.
# All GGUF models are served via llama-cpp-python (llamacpp backend).
# ONNX models use onnxruntime-genai (onnx backend).

REGISTRY: list[ModelProfile] = [

    # ── Tier 1 · Speed (≥15 tok/s) ──────────────────────────────────────────

    ModelProfile(
        id="phi4mini-onnx",
        name="Phi-4-mini INT4 (ONNX)",
        hf_repo="microsoft/Phi-4-mini-instruct-onnx",
        hf_filename=None,  # directory: cpu-int4-rtn-block-32
        backend="onnx",
        quant="INT4",
        params_b=3.8,
        active_params_b=3.8,
        ram_gb=2.5,
        tok_per_sec_8core=20.0,
        ctx_k=128,
        thinking_mode=False,
        multilingual=True,
        astronomy_specialist=False,
        notes="Microsoft's Phi-4-mini in ONNX INT4. Fastest option; excellent reasoning. "
              "onnxruntime-genai delivers ~5-12x speedup over vanilla PyTorch on CPU.",
        download_cmd=(
            "hf download microsoft/Phi-4-mini-instruct-onnx "
            "--include 'cpu-int4-rtn-block-32/*' "
            "--local-dir models/phi4mini-onnx"
        ),
    ),

    ModelProfile(
        id="qwen3-1.7b",
        name="Qwen3-1.7B Q8_0",
        hf_repo="Qwen/Qwen3-1.7B-GGUF",
        hf_filename="Qwen3-1.7B-Q8_0.gguf",
        backend="llamacpp",
        quant="Q8_0",
        params_b=1.7,
        active_params_b=1.7,
        ram_gb=1.5,
        tok_per_sec_8core=18.0,
        ctx_k=32,
        thinking_mode=True,
        multilingual=True,
        astronomy_specialist=False,
        notes="Ultra-fast. Thinking mode already supported by HAL's <think> stripper.",
        download_cmd=(
            "hf download Qwen/Qwen3-1.7B-GGUF "
            "Qwen3-1.7B-Q8_0.gguf --local-dir models/"
        ),
    ),

    # ── Tier 2 · Balanced (5–15 tok/s) ──────────────────────────────────────

    ModelProfile(
        id="qwen3-4b",
        name="Qwen3-4B Q4_K_M",
        hf_repo="Qwen/Qwen3-4B-GGUF",
        hf_filename="Qwen3-4B-Q4_K_M.gguf",
        backend="llamacpp",
        quant="Q4_K_M",
        params_b=4.0,
        active_params_b=4.0,
        ram_gb=2.8,
        tok_per_sec_8core=10.0,
        ctx_k=32,
        thinking_mode=True,
        multilingual=True,
        astronomy_specialist=False,
        notes="Best all-round Pareto point. Strong reasoning + thinking mode + Spanish.",
        download_cmd=(
            "hf download Qwen/Qwen3-4B-GGUF "
            "Qwen3-4B-Q4_K_M.gguf --local-dir models/"
        ),
    ),

    ModelProfile(
        id="astrosage-8b",
        name="AstroSage-LLaMA-3.1-8B Q4_K_M",
        hf_repo="AstroMLab/AstroSage-LLaMA-3.1-8B-GGUF",
        hf_filename="AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf",
        backend="llamacpp",
        quant="Q4_K_M",
        params_b=8.1,
        active_params_b=8.1,
        ram_gb=5.0,
        tok_per_sec_8core=6.0,
        ctx_k=128,
        thinking_mode=False,
        multilingual=False,
        astronomy_specialist=True,
        notes="Fine-tuned on astronomy literature. Scores at GPT-4o level on AstroMLab-1 "
              "benchmark (80.9%). Best domain accuracy for HAL9000.",
        download_cmd=(
            "hf download AstroMLab/AstroSage-LLaMA-3.1-8B-GGUF "
            "AstroSage-LLaMA-3.1-8B-Q4_K_M.gguf --local-dir models/"
        ),
    ),

    # ── Tier 3 · Quality (2–5 tok/s) — MoE gems ──────────────────────────────

    ModelProfile(
        id="qwen3-30b-moe",
        name="Qwen3-30B-A3B Q4_K_M (MoE)",
        hf_repo="Qwen/Qwen3-30B-A3B-GGUF",
        hf_filename="Qwen3-30B-A3B-Q4_K_M.gguf",
        backend="llamacpp",
        quant="Q4_K_M",
        params_b=30.0,
        active_params_b=3.0,
        ram_gb=8.5,
        tok_per_sec_8core=8.0,   # MoE: fast despite 30B total params
        ctx_k=128,
        thinking_mode=True,
        multilingual=True,
        astronomy_specialist=False,
        notes="Mixture-of-Experts: 30B total params but only 3B active per token. "
              "Speed of a 3B model with quality of a 30B. SOTA Pareto point. "
              "Abliterated (uncensored) variant: huihui-ai/Qwen3-30B-A3B-abliterated-GGUF",
        download_cmd=(
            "hf download Qwen/Qwen3-30B-A3B-GGUF "
            "Qwen3-30B-A3B-Q4_K_M.gguf --local-dir models/"
        ),
    ),

    ModelProfile(
        id="qwen3-30b-moe-abliterated",
        name="Qwen3-30B-A3B abliterated Q4_K_M (MoE)",
        hf_repo="huihui-ai/Qwen3-30B-A3B-abliterated-GGUF",
        hf_filename="Qwen3-30B-A3B-abliterated-Q4_K_M.gguf",
        backend="llamacpp",
        quant="Q4_K_M",
        params_b=30.0,
        active_params_b=3.0,
        ram_gb=8.5,
        tok_per_sec_8core=8.0,
        ctx_k=128,
        thinking_mode=True,
        multilingual=True,
        astronomy_specialist=False,
        notes="huihui-ai abliterated (uncensored) variant of Qwen3-30B-A3B. "
              "Removes refusals without degrading accuracy. Ideal for observatory "
              "technical queries where model alignment might block edge-case commands.",
        download_cmd=(
            "hf download huihui-ai/Qwen3-30B-A3B-abliterated-GGUF "
            "Qwen3-30B-A3B-abliterated-Q4_K_M.gguf --local-dir models/"
        ),
    ),

    ModelProfile(
        id="qwen3-8b",
        name="Qwen3-8B Q4_K_M",
        hf_repo="Qwen/Qwen3-8B-GGUF",
        hf_filename="Qwen3-8B-Q4_K_M.gguf",
        backend="llamacpp",
        quant="Q4_K_M",
        params_b=8.0,
        active_params_b=8.0,
        ram_gb=5.0,
        tok_per_sec_8core=5.5,
        ctx_k=128,
        thinking_mode=True,
        multilingual=True,
        astronomy_specialist=False,
        notes="Dense 8B, thinking mode, multilingual. Strong reasoning.",
        download_cmd=(
            "hf download Qwen/Qwen3-8B-GGUF "
            "Qwen3-8B-Q4_K_M.gguf --local-dir models/"
        ),
    ),
]

REGISTRY_BY_ID: dict[str, ModelProfile] = {m.id: m for m in REGISTRY}


# ── Recommendation engine ─────────────────────────────────────────────────────


def recommend(
    ram_gb: float = 8.0,
    cores: int = 8,
    priority: Literal["speed", "balanced", "quality", "astronomy"] = "balanced",
) -> ModelProfile:
    """Return the best model profile for the given hardware + priority."""
    candidates = [m for m in REGISTRY if m.ram_gb <= ram_gb * 0.85]
    if not candidates:
        candidates = [min(REGISTRY, key=lambda m: m.ram_gb)]

    if priority == "speed":
        return max(candidates, key=lambda m: m.tok_per_sec_8core)

    if priority == "astronomy":
        astro = [m for m in candidates if m.astronomy_specialist]
        if astro:
            return max(astro, key=lambda m: m.params_b)
        # fall through to balanced if no astronomy model fits RAM

    if priority == "quality":
        # Prefer MoE models since they punch above their weight
        moe = [m for m in candidates if m.is_moe]
        if moe:
            return max(moe, key=lambda m: m.params_b)
        return max(candidates, key=lambda m: m.params_b)

    # "balanced": maximize tok/s × log(quality) proxy
    def score(m: ModelProfile) -> float:
        quality_proxy = m.active_params_b * (2.0 if m.astronomy_specialist else 1.0)
        return m.tok_per_sec_8core * (quality_proxy ** 0.5)

    return max(candidates, key=score)


def pareto_table() -> str:
    """Return a formatted text table of the Pareto frontier for logging."""
    lines = [
        f"{'ID':<30} {'Backend':<10} {'Params':>8} {'Active':>7} {'RAM':>6} {'tok/s':>7} {'Notes'}",
        "-" * 110,
    ]
    for m in REGISTRY:
        moe = " [MoE]" if m.is_moe else ""
        astro = " ★astro" if m.astronomy_specialist else ""
        lines.append(
            f"{m.id:<30} {m.backend:<10} {m.params_b:>6.0f}B {m.active_params_b:>5.1f}B "
            f"{m.ram_gb:>5.1f}G {m.tok_per_sec_8core:>6.1f}/s  {m.quant}{moe}{astro}"
        )
    return "\n".join(lines)
