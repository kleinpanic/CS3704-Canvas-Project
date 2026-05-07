# Usage: docker run -e CANVAS_TOKEN=xxx -e CANVAS_BASE_URL=https://canvas.vt.edu ghcr.io/kleinpanic/canvas-tui
# tag: python:3.12-slim
FROM python:3.12-slim@sha256:46cb7cc2877e60fbd5e21a9ae6115c30ace7a077b9f8772da879e4590c18c2e3

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
