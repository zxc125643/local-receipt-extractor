#!/usr/bin/env bash
set -euo pipefail

exec /home/yi/llama.cpp-qwen38/build/bin/llama-server \
  --model /home/yi/models/Qwen3.8-27B-ABLITERATED-GGUF/Qwen3.8-27B-ABLITERATED-Q6_K.gguf \
  --mmproj /home/yi/models/Qwen3.8-27B-ABLITERATED-GGUF/mmproj-Qwen3.8-27B-ABLITERATED-F16.gguf \
  --alias qwen3.8-27b-abliterated-q6-k \
  --host 0.0.0.0 \
  --port 8001 \
  --timeout 7200 \
  --sleep-idle-seconds -1 \
  --ctx-size 131072 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --batch-size 1024 \
  --ubatch-size 512 \
  --parallel 1 \
  --predict 8192 \
  --n-gpu-layers all \
  --split-mode tensor \
  --tensor-split 1,1 \
  --fit off \
  --mmproj-offload \
  --image-min-tokens 1024 \
  --image-max-tokens 4096 \
  --flash-attn on \
  --spec-type draft-mtp \
  --spec-draft-n-max 3 \
  --reasoning-preserve \
  --jinja \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20
