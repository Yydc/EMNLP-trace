#!/bin/bash

# Build TraceBench using Together AI
# Model: Qwen/Qwen3-235B-A22B-Instruct-2507-tput

export TOGETHER_API_KEY="4f7c26f29d3edfbe1f981d4fa4c812c36107fac22bd6bb35158b02138ac6785d"

python scripts/build_tracebench.py \
  --provider together \
  --model "Qwen/Qwen3-235B-A22B-Instruct-2507-tput" \
  --output data/tracebench_together \
  --target-turns 8 \
  --rollbacks 2 \
  --noisy-rationales 3 \
  --limit 10

echo ""
echo "=== Build Complete ==="
echo "Output directory: data/tracebench_together"
