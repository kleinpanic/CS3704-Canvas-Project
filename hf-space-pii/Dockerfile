FROM python:3.11-slim@sha256:6d85378d88a19cd4d76079817532d62232be95757cb45945a99fec8e8084b9c2  # 3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Preload the Piiranha model at build time so cold-start is just container wake,
# not model download. HF_TOKEN not needed — model is public.
RUN python - <<'EOF'
from transformers import pipeline
pipeline(
    "token-classification",
    model="iiiorg/piiranha-v1-detect-personal-information",
    aggregation_strategy="simple",
)
print("Piiranha preloaded.")
EOF

COPY app.py .

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
