# Gemma 2B Reranker — Training Container
# CUDA 12.4, Python 3.10, HuggingFace stack + llama.cpp for GGUF export
#
# Build on Brev (has GPU + storage):
#   docker build -t gemma2b-trainer -f Gemma2B-Reranker/docker/Dockerfile .
#
# Run training:
#   docker run --gpus all --ipc=host --shm-size=8g \
#       -v /workspace:/workspace \
#       -e HF_TOKEN \
#       -e WANDB_API_KEY \
#       gemma2b-trainer python3 /workspace/scripts/train_gemma2b.py

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    curl \
    wget \
    build-essential \
    cmake \
    pkg-config \
    libssl-dev \
    libffi-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python

# ── PyTorch (CUDA 12.4) ───────────────────────────────────────────────────────
RUN pip install \
    torch==2.4.1 \
    torchvision==0.19.1 \
    torchaudio==2.4.1 \
    --index-url https://download.pytorch.org/whl/cu124

# ── HuggingFace Core ────────────────────────────────────────────────────────────
RUN pip install \
    transformers==4.46.3 \
    peft==0.13.2 \
    bitsandbytes==0.44.1 \
    accelerate==0.34.0 \
    datasets==3.2.0 \
    huggingface_hub==0.26.3 \
    trl==0.12.2

# ── Training extras ────────────────────────────────────────────────────────────
RUN pip install \
    tensorboard \
    scipy

# ── llama.cpp (for GGUF export) ─────────────────────────────────────────────
WORKDIR /tmp/llama.cpp
RUN git clone --depth 1 https://github.com/ggerganov/llama.cpp && \
    cd llama.cpp && \
    cmake . -DLLAMA_CUBLAS=ON -DCMAKE_CUDA_ARCHITECTURES="80;86;89;90;100" && \
    make -j$(nproc) && \
    cp quantize /usr/local/bin/ && \
    cp convert_hf_to_gguf.py /usr/local/bin/ && \
    cd / && rm -rf /tmp/llama.cpp

WORKDIR /workspace

CMD ["bash"]
