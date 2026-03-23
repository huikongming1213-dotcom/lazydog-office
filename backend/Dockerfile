FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv --no-cache-dir

# Copy dependency manifest first (layer caching)
COPY pyproject.toml .

# Create a minimal package structure so uv can install
COPY backend/ ./backend/

# Install production dependencies only
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
