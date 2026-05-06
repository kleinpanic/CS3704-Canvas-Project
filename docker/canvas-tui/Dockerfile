# Usage: docker run -e CANVAS_TOKEN=xxx -e CANVAS_BASE_URL=https://canvas.vt.edu ghcr.io/kleinpanic/canvas-tui
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/canvas_tui/ ./src/canvas_tui/

RUN pip install --no-cache-dir .

ENV CANVAS_BASE_URL=""
ENV CANVAS_TOKEN=""

ENTRYPOINT ["canvas-tui"]
CMD ["--help"]
