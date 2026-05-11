#!/usr/bin/env python3
"""Benchmark the active HAL9000 LLM backend.

Runs a warm-up + timed generation sequence and reports:
  - tokens/second
  - time to first token (TTFT)
  - total generation time
  - context window

Usage:
  python3 scripts/benchmark_llm.py [--url http://localhost:8000/api/llm/v1]
                                    [--model llamacpp]
                                    [--tokens 200]
                                    [--runs 3]

Requires the backend to be running (./start.sh first).
"""
import argparse
import json
import statistics
import sys
import time
import urllib.request

ASTRONOMY_PROMPT = (
    "Explain the difference between apparent and absolute magnitude of a star, "
    "and give me the formula to convert between them. Be concise."
)


def stream_tokens(base_url: str, model: str, prompt: str, max_tokens: int) -> tuple[float, float, int]:
    """Returns (time_to_first_token, total_time, token_count)."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": True,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    ttft = None
    token_count = 0

    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            line = line.decode().strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    token_count += len(delta.split())  # rough token estimate
                    sys.stdout.write(delta)
                    sys.stdout.flush()
            except (json.JSONDecodeError, KeyError):
                continue

    total = time.perf_counter() - t0
    print()
    return ttft or total, total, token_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/api/llm/v1")
    ap.add_argument("--model", default="llamacpp")
    ap.add_argument("--tokens", type=int, default=200)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--prompt", default=ASTRONOMY_PROMPT)
    args = ap.parse_args()

    print("━" * 60)
    print(f"  HAL9000 LLM Benchmark")
    print(f"  URL    : {args.url}")
    print(f"  Model  : {args.model}")
    print(f"  Tokens : {args.tokens}")
    print(f"  Runs   : {args.runs}")
    print("━" * 60)
    print(f"Prompt: {args.prompt}\n")

    # Warm-up
    print("── Warm-up run ──")
    try:
        stream_tokens(args.url, args.model, args.prompt, min(50, args.tokens))
    except Exception as e:
        print(f"\n[!] Connection failed: {e}")
        print(f"    Make sure the backend is running: ./start.sh")
        sys.exit(1)

    print("\n── Timed runs ──")
    ttfts, totals, tps_list = [], [], []
    for i in range(args.runs):
        print(f"\n--- Run {i+1}/{args.runs} ---")
        ttft, total, n_tok = stream_tokens(args.url, args.model, args.prompt, args.tokens)
        ttfts.append(ttft)
        totals.append(total)
        tps = n_tok / total if total > 0 else 0
        tps_list.append(tps)
        print(f"  TTFT={ttft:.2f}s  total={total:.2f}s  ~{tps:.1f} tok/s  ({n_tok} words)")

    print("\n━" * 60)
    print("  Results (median over timed runs):")
    print(f"  Time to first token : {statistics.median(ttfts):.2f} s")
    print(f"  Total time          : {statistics.median(totals):.2f} s")
    print(f"  Throughput          : ~{statistics.median(tps_list):.1f} words/s")
    print()

    # Compare against registry
    try:
        sys.path.insert(0, str(__file__ + "/../.."))
        from backend.app.services.model_registry import pareto_table
        print("  CPU model Pareto table:\n")
        print(pareto_table())
    except ImportError:
        pass
    print("━" * 60)


if __name__ == "__main__":
    main()
