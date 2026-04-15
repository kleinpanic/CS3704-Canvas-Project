#!/usr/bin/env bash
# Gemma 2B Reranker — Docker runner
# Usage: ./run.sh [bash|train|download]
#
# Mounts the Gemma2B-Reranker workspace into the container.
# Requires: nvidia-docker (nvidia-container-toolkit)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="${IMAGE_NAME:-gemma2b-reranker}"
CONTAINER_NAME="${CONTAINER_NAME:-gemma2b-reranker-dev}"

GPU_FLAG="--gpus all"
WORKSPACE_MOUNT="-v ${PROJECT_DIR}:/workspace"
WORKSPACE_DIR="-w /workspace"

# Detect CUDA compute capability for llama-cpp-python extra index
CUDA_ARCH=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d . || echo "")
if [[ "$CUDA_ARCH" == "89" ]] || [[ "$CUDA_ARCH" == "90" ]]; then
    # RTX 5090 (compute 10.0) or new Blackwell — use cu124
    LLAMA_EXTRA_INDEX="https://abetlen.github.io/llama-cpp-python/whl/cu124"
elif [[ "$CUDA_ARCH" == "86" ]] || [[ "$CUDA_ARCH" == "89" ]]; then
    # Ampere (A4000/A6000/L40S) or Ada (L4/RTX 4090) — use cu124
    LLAMA_EXTRA_INDEX="https://abetlen.github.io/llama-cpp-python/whl/cu124"
else
    # Fallback
    LLAMA_EXTRA_INDEX="https://abetlen.github.io/llama-cpp-python/whl/cu124"
fi

run_interactive() {
    echo "[INFO] Starting interactive shell in ${IMAGE_NAME}..."
    echo "[INFO] Project dir: ${PROJECT_DIR}"
    echo "[INFO] GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'unknown')"
    docker run --rm -it \
        ${GPU_FLAG} \
        ${WORKSPACE_MOUNT} \
        ${WORKSPACE_DIR} \
        --name "${CONTAINER_NAME}" \
        --shm-size=8gb \
        --ulimit memlock=-1 \
        --env HuggingFaceToken="${HF_TOKEN:-}" \
        --env WANDB_API_KEY \
        "${IMAGE_NAME}" \
        bash
}

run_train() {
    echo "[INFO] Running training script..."
    docker run --rm \
        ${GPU_FLAG} \
        ${WORKSPACE_MOUNT} \
        ${WORKSPACE_DIR} \
        --name "${CONTAINER_NAME}" \
        --shm-size=8gb \
        --ulimit memlock=-1 \
        --env HuggingFaceToken="${HF_TOKEN:-}" \
        --env WANDB_API_KEY \
        --env HF_TOKEN \
        "${IMAGE_NAME}" \
        python3 scripts/finetune_reranker.py --action train "$@"
}

case "${1:-bash}" in
    bash|i|"-i"|"--interactive")
        run_interactive
        ;;
    train|t)
        shift; run_train "$@"
        ;;
    build|b)
        echo "[INFO] Building ${IMAGE_NAME}..."
        docker build -t "${IMAGE_NAME}" "$(dirname "$0")"
        ;;
    gpu|g)
        nvidia-smi
        ;;
    *)
        echo "Usage: $0 {bash|train|build|gpu}"
        exit 1
        ;;
esac
