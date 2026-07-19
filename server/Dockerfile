FROM python:3.12-slim

# Install uv for fast dependency resolution.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy package metadata and install the package without a separate build step.
COPY pyproject.toml .
COPY app/ ./app/
RUN uv pip install --system .

# Data directory: persist via volume.
ENV VIBE_DATA_DIR=/data
ENV VIBE_DATABASE_URL=sqlite:////data/app.db
EXPOSE 8000
VOLUME ["/data"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
