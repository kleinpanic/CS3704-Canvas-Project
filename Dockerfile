FROM python:3.12-slim

LABEL maintainer="Collin Schaufele <kleinpanic@proton.me>"
LABEL description="Canvas LMS TUI client"

WORKDIR /app

# Install pdftotext for syllabus preview
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Copy and install
COPY . .
RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd -m -s /bin/bash canvas
USER canvas

# Create data directories
RUN mkdir -p ~/.local/share/canvas-tui ~/.config/canvas-tui

ENTRYPOINT ["canvas-tui"]
