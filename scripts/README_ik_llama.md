# Running HAL on `ik_llama.cpp`

`ik_llama.cpp` is Iwan Kawrakow's fork of `llama.cpp` with state-of-the-art
quantization (IQK / Trellis) and faster CPU + hybrid GPU inference. On an
RTX 3070 Ti running a 7B-class model, you can expect ~30–50% higher t/s than
mainline Ollama for the same GGUF, plus access to higher-quality 4-bit and
3-bit quants that don't exist outside this fork.

HAL is backend-agnostic: both Ollama and `ik_llama.cpp`'s `llama-server`
expose an OpenAI-compatible `/v1/chat/completions` endpoint, so switching
between them is a single env var.

## 1. Build it

```bash
# From the repo root.  Builds with CUDA (sm_86 = Ampere / 3070-3090) by default.
./scripts/setup_ik_llama.sh
```

The script installs build deps, clones to `~/ik_llama.cpp`, and builds the
`llama-server` target. Override:

| Env var      | Default              | Notes                                   |
| ------------ | -------------------- | --------------------------------------- |
| `REPO_DIR`   | `~/ik_llama.cpp`     | Where to clone + build                  |
| `WITH_CUDA`  | `1`                  | Set to `0` for CPU-only build           |
| `CUDA_ARCH`  | `86`                 | `89` for 4090, `80` for A100, etc.      |
| `JOBS`       | `nproc`              | Parallel build jobs                     |

## 2. Drop a GGUF model in

```bash
cd ~/ik_llama.cpp/models
# 7B Instruct, IQ4_XS — ~4.4 GB, fits on 8 GB VRAM with 8k context
curl -LO https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-IQ4_XS.gguf
```

Other sensible picks for the RTX 3070 Ti:
- `Qwen2.5-7B-Instruct-IQ3_M.gguf` — smaller, more headroom for context
- `Qwen2.5-3B-Instruct-Q5_K_M.gguf` — much faster, slightly weaker reasoning

## 3. Start the server

```bash
./scripts/run_ik_llama.sh
```

Defaults: bind `127.0.0.1:8080`, full GPU offload (`-ngl 999`), 8k context.
First-found `.gguf` in `~/ik_llama.cpp/models` is loaded automatically.

Override knobs as needed:
```bash
MODEL=/path/to/other.gguf CTX=16384 NGL=20 ./scripts/run_ik_llama.sh
```

## 4. Switch HAL to `ik_llama`

In `.env`:
```ini
LLM_BACKEND=ik_llama
IK_LLAMA_BASE_URL=http://localhost:8080
```

Restart the backend. The factory in `backend/app/agent/llm.py` will route
both the `instructor` extraction client *and* the streaming `ChatOpenAI`
through `localhost:8080/v1`. To go back to Ollama, set
`LLM_BACKEND=ollama` (or remove the line).

## How it slots into the pipeline

```
HAL graph (LangGraph)
    │
    ├── intent_classifier ┐
    ├── planner           │
    ├── tool_executor     │ ─── instructor.from_openai( OpenAI(base_url=…/v1) )
    │   (extract_tool_args)
    │
    └── _stream_response ──── ChatOllama  | ChatOpenAI
                              (Ollama)    | (ik_llama)
```

`get_instructor_client()` and `make_streaming_llm()` in
`backend/app/agent/llm.py` are the two switchpoints. Everything else in the
graph is identical between backends.

## Caveats

- **`-rtr` flag**: don't enable it. `run_ik_llama.sh` doesn't. It repacks
  CPU-resident tensors and forces matmuls onto CPU when a quant lacks a CUDA
  implementation, which tanks throughput on a discrete GPU.
- **Per-request `num_ctx` is Ollama-only**. On `ik_llama`, the context
  window is fixed at server launch (`--ctx-size`). The factory still passes
  `num_predict` (mapped to `max_tokens`) so reply length isn't capped.
- **First request is slow**. The model has to load into VRAM. After that,
  subsequent generations run at full speed.
