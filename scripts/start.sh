#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR" || exit 1

python3 server.py \
    --model-path /Users/mlamp/PretrainedModels/octoasr/OctoASR-1.7B-Instruct-1.0-MLX-8bit \
    --vad-model-path ~/.octoasr/models/fsmn-vad-mlx \
    --host 0.0.0.0 \
    --port 8787 \
    --load-on-startup


# /Users/mlamp/.octoasr/models/Mininglamp-2718/OctoASR-0.8B-Instruct-1.0-MLX-8bit
# /Users/mlamp/PretrainedModels/octoasr/OctoASR-1.7B-Instruct-1.0-MLX-8bit
# 