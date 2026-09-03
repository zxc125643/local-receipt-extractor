#!/usr/bin/env bash
set -euo pipefail
cd /home/yi/vLLM-2080Ti-Definitive
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_HOME=/usr/local/cuda-12.8
export CUDA_PATH=/usr/local/cuda-12.8
export CUDA_VISIBLE_DEVICES=0,1
export TORCH_CUDA_ARCH_LIST=7.5
export TORCH_EXTENSIONS_DIR=/home/yi/vLLM-2080Ti-Definitive/.deps/FlashQLA-SM70-SM75/.torch_extensions_vllm_flashqla_legacy
export TRITON_CACHE_DIR=/home/yi/vLLM-2080Ti-Definitive/triton-cache
export VLLM_ALLOW_MAMBA_SPEC_FULL_CUDAGRAPH=0
export VLLM_ENFORCE_STRICT_TOOL_CALLING=1
exec /home/yi/vLLM-2080Ti-Definitive/.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 --port 8001 \
  --model /home/yi/models/Qwen3.8-27B-Uncensored-Q6_K-GGUF/Qwen3.8-27B-Uncensored-Q6_K.gguf \
  --tokenizer /home/yi/models/Huihui-Qwen3.8-27B-abliterated-FP8 \
  --hf-config-path /home/yi/models/Qwen3.8-27B-Uncensored-Q6_K-GGUF/hf-text-config \
  --served-model-name qwen38-27b-q6-vllm \
  --dtype half --tensor-parallel-size 2 --generation-config /home/yi/models/Huihui-Qwen3.8-27B-abliterated-FP8 \
  --max-model-len 122880 --enable-chunked-prefill \
  --max-num-seqs 1 --max-num-batched-tokens 2048 \
  --gpu-memory-utilization 0.90 \
  --mamba-cache-mode align --enable-prefix-caching --enable-prompt-tokens-details \
  --disable-log-stats --language-model-only --skip-mm-profiling \
  --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking":true}' \
  --tool-call-parser qwen3_xml --enable-auto-tool-choice \
  --additional-config '{"gdn_prefill_backend":"flashqla_legacy"}' \
  --compilation-config '{"cudagraph_mode":"PIECEWISE","cudagraph_capture_sizes":[4],"max_cudagraph_capture_size":4}'
